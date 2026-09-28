# SPDX-License-Identifier: Apache-2.0

import io
import os.path

import b2sdk.v2
import b2sdk.v2.exception
import boto3.session
import botocore.exceptions
import google.cloud.storage
import pytest

from pyramid.httpexceptions import HTTPForbidden
from zope.interface.verify import verifyClass

import warehouse.packaging.services

from warehouse.admin.flags import AdminFlag, AdminFlagValue
from warehouse.constants import RateLimitPeriod
from warehouse.organizations.models import OrganizationProject
from warehouse.packaging.interfaces import (
    IDocsStorage,
    IFileStorage,
    IProjectService,
    ISimpleStorage,
    ProjectNameUnavailableExistingError,
    ProjectNameUnavailableInvalidError,
    ProjectNameUnavailableProhibitedError,
    ProjectNameUnavailableSimilarError,
    ProjectNameUnavailableStdlibError,
    TooManyProjectsCreated,
)
from warehouse.packaging.models import Role
from warehouse.packaging.services import (
    B2FileStorage,
    GCSFileStorage,
    GCSSimpleStorage,
    GenericLocalBlobStorage,
    LocalArchiveFileStorage,
    LocalDocsStorage,
    LocalFileStorage,
    LocalSimpleStorage,
    ProjectService,
    S3ArchiveFileStorage,
    S3DocsStorage,
    S3FileStorage,
    project_service_factory,
)
from warehouse.packaging.tasks import typo_check_project_name
from warehouse.rate_limiting import DummyRateLimiter
from warehouse.rate_limiting.interfaces import WindowStats

from ...common.db.accounts import UserFactory
from ...common.db.organizations import OrganizationFactory
from ...common.db.packaging import ProhibitedProjectFactory, ProjectFactory


@pytest.fixture
def service_request(mocker):
    """Build the (settings, find_service) pair a ``create_service`` reads."""

    def _service_request(settings, service=None):
        request = mocker.Mock(spec=["find_service", "registry"])
        request.find_service.return_value = service
        request.registry.settings = settings
        return request

    return _service_request


@pytest.fixture
def upload_file(tmpdir):
    """Write a file for a storage to upload, returning its path."""

    def _upload_file(contents=b"Test File!", name="testfile.txt"):
        path = str(tmpdir.join(name))
        with open(path, "wb") as fp:
            fp.write(contents)
        return path

    return _upload_file


@pytest.fixture
def gcs_blob(mocker):
    blob = mocker.create_autospec(google.cloud.storage.Blob, instance=True)
    blob.exists.return_value = False
    return blob


@pytest.fixture
def gcs_bucket(mocker, gcs_blob):
    bucket = mocker.create_autospec(google.cloud.storage.Bucket, instance=True)
    bucket.blob.return_value = gcs_blob
    return bucket


class TestLocalFileStorage:
    def test_verify_service(self):
        assert verifyClass(IFileStorage, LocalFileStorage)

    def test_basic_init(self):
        storage = LocalFileStorage("/foo/bar/")
        assert storage.base == "/foo/bar/"

    def test_create_service(self, service_request):
        request = service_request({"files.path": "/the/one/two/"})

        storage = LocalFileStorage.create_service(None, request)

        assert storage.base == "/the/one/two/"

    def test_gets_file(self, tmpdir):
        with open(str(tmpdir.join("file.txt")), "wb") as fp:
            fp.write(b"my test file contents")

        storage = LocalFileStorage(str(tmpdir))
        file_object = storage.get("file.txt")
        assert file_object.read() == b"my test file contents"
        file_object.close()

    def test_raises_when_file_non_existent(self, tmpdir):
        storage = LocalFileStorage(str(tmpdir))
        with pytest.raises(FileNotFoundError):
            storage.get("file.txt")

    def test_stores_file(self, tmpdir, upload_file):
        filename = upload_file()

        storage_dir = str(tmpdir.join("storage"))
        storage = LocalFileStorage(storage_dir)
        storage.store("foo/bar.txt", filename)

        with open(os.path.join(storage_dir, "foo/bar.txt"), "rb") as fp:
            assert fp.read() == b"Test File!"

    def test_stores_and_gets_metadata(self, tmpdir, upload_file):
        filename = upload_file()

        storage_dir = str(tmpdir.join("storage"))
        storage = LocalFileStorage(storage_dir)
        storage.store("foo/bar.txt", filename, meta={"foo": "bar", "wu": "tang"})

        with open(os.path.join(storage_dir, "foo/bar.txt"), "rb") as fp:
            assert fp.read() == b"Test File!"
        with open(os.path.join(storage_dir, "foo/bar.txt.meta"), "rb") as fp:
            assert fp.read() == b'{"foo": "bar", "wu": "tang"}'

        assert storage.get_metadata("foo/bar.txt") == {"foo": "bar", "wu": "tang"}

    def test_gets_size(self, tmpdir, upload_file):
        filename = upload_file()

        storage_dir = str(tmpdir.join("storage"))
        storage = LocalFileStorage(storage_dir)
        storage.store("foo/bar.txt", filename)

        assert storage.get_size("foo/bar.txt") == len(b"Test File!")

    def test_get_size_raises_when_file_non_existent(self, tmpdir):
        storage = LocalFileStorage(str(tmpdir.join("storage")))

        with pytest.raises(FileNotFoundError):
            storage.get_size("foo/bar.txt")

    def test_stores_two_files(self, tmpdir, upload_file):
        filename1 = upload_file(b"First Test File!", "testfile1.txt")
        filename2 = upload_file(b"Second Test File!", "testfile2.txt")

        storage_dir = str(tmpdir.join("storage"))
        storage = LocalFileStorage(storage_dir)
        storage.store("foo/first.txt", filename1)
        storage.store("foo/second.txt", filename2)

        with open(os.path.join(storage_dir, "foo/first.txt"), "rb") as fp:
            assert fp.read() == b"First Test File!"

        with open(os.path.join(storage_dir, "foo/second.txt"), "rb") as fp:
            assert fp.read() == b"Second Test File!"


class TestLocalArchiveFileStorage:
    def test_verify_service(self):
        assert verifyClass(IFileStorage, LocalArchiveFileStorage)

    def test_create_service(self, service_request):
        request = service_request({"archive_files.path": "/the/one/two/"})

        storage = LocalArchiveFileStorage.create_service(None, request)

        assert storage.base == "/the/one/two/"


class TestLocalDocsStorage:
    def test_verify_service(self):
        assert verifyClass(IDocsStorage, LocalDocsStorage)

    def test_create_service(self, service_request):
        request = service_request({"docs.path": "/the/one/two/"})

        storage = LocalDocsStorage.create_service(None, request)

        assert storage.base == "/the/one/two/"

    def test_delete_by_prefix(self, tmpdir):
        storage_dir = str(tmpdir.join("storage"))
        os.makedirs(os.path.join(storage_dir, "foo"), exist_ok=True)
        os.makedirs(os.path.join(storage_dir, "bar"), exist_ok=True)

        filename0 = str(tmpdir.join("storage/foo/testfile0.txt"))
        with open(filename0, "wb") as fp:
            fp.write(b"Zeroth Test File!")

        filename1 = str(tmpdir.join("storage/foo/testfile1.txt"))
        with open(filename1, "wb") as fp:
            fp.write(b"First Test File!")

        filename2 = str(tmpdir.join("storage/bar/testfile2.txt"))
        with open(filename2, "wb") as fp:
            fp.write(b"Second Test File!")

        storage = LocalDocsStorage(storage_dir)
        storage.remove_by_prefix("foo")

        assert not os.path.exists(os.path.join(storage_dir, "foo"))

        with open(os.path.join(storage_dir, "bar/testfile2.txt"), "rb") as fp:
            assert fp.read() == b"Second Test File!"

    def test_delete_already_gone(self, tmpdir):
        storage_dir = str(tmpdir.join("storage"))
        storage = LocalDocsStorage(storage_dir)

        response = storage.remove_by_prefix("foo")
        assert response is None


class TestLocalSimpleStorage:
    def test_verify_service(self):
        assert verifyClass(ISimpleStorage, LocalSimpleStorage)

    def test_basic_init(self):
        storage = LocalSimpleStorage("/foo/bar/")
        assert storage.base == "/foo/bar/"

    def test_create_service(self, service_request):
        request = service_request({"simple.path": "/simple/one/two/"})

        storage = LocalSimpleStorage.create_service(None, request)

        assert storage.base == "/simple/one/two/"

    def test_gets_file(self, tmpdir):
        with open(str(tmpdir.join("file.txt")), "wb") as fp:
            fp.write(b"my test file contents")

        storage = LocalSimpleStorage(str(tmpdir))
        file_object = storage.get("file.txt")
        assert file_object.read() == b"my test file contents"
        file_object.close()

    def test_raises_when_file_non_existent(self, tmpdir):
        storage = LocalSimpleStorage(str(tmpdir))
        with pytest.raises(FileNotFoundError):
            storage.get("file.txt")

    def test_stores_file(self, tmpdir, upload_file):
        filename = upload_file()

        storage_dir = str(tmpdir.join("storage"))
        storage = LocalSimpleStorage(storage_dir)
        storage.store("foo/bar.txt", filename)

        with open(os.path.join(storage_dir, "foo/bar.txt"), "rb") as fp:
            assert fp.read() == b"Test File!"

    def test_stores_two_files(self, tmpdir, upload_file):
        filename1 = upload_file(b"First Test File!", "testfile1.txt")
        filename2 = upload_file(b"Second Test File!", "testfile2.txt")

        storage_dir = str(tmpdir.join("storage"))
        storage = LocalSimpleStorage(storage_dir)
        storage.store("foo/first.txt", filename1)
        storage.store("foo/second.txt", filename2)

        with open(os.path.join(storage_dir, "foo/first.txt"), "rb") as fp:
            assert fp.read() == b"First Test File!"

        with open(os.path.join(storage_dir, "foo/second.txt"), "rb") as fp:
            assert fp.read() == b"Second Test File!"


class TestB2FileStorage:
    @pytest.fixture
    def b2_bucket(self, mocker):
        return mocker.create_autospec(b2sdk.v2.Bucket, instance=True)

    @pytest.fixture
    def b2_api(self, mocker, b2_bucket):
        api = mocker.create_autospec(b2sdk.v2.B2Api, instance=True)
        api.get_bucket_by_name.return_value = b2_bucket
        return api

    @pytest.fixture
    def b2_request(self, service_request, b2_api):
        return service_request({"files.bucket": "froblob"}, b2_api)

    @pytest.fixture
    def b2_storage(self, b2_request):
        return B2FileStorage.create_service(None, b2_request)

    def test_verify_service(self):
        assert verifyClass(IFileStorage, B2FileStorage)

    def test_basic_init(self, b2_bucket):
        storage = B2FileStorage(b2_bucket, prefix="segakcap")

        assert storage.bucket is b2_bucket
        assert storage.prefix == "segakcap"

    def test_create_service(self, b2_api, b2_bucket, b2_request, b2_storage):
        b2_request.find_service.assert_called_once_with(name="b2.api")
        b2_api.get_bucket_by_name.assert_called_once_with("froblob")
        assert b2_storage.bucket is b2_bucket

    def test_gets_file(self, b2_bucket, b2_storage):
        b2_bucket.download_file_by_name.return_value.save.side_effect = (
            lambda file_obj: file_obj.write(b"my contents")
        )

        file_object = b2_storage.get("file.txt")

        assert file_object.read() == b"my contents"
        b2_bucket.download_file_by_name.assert_called_once_with("file.txt")

    def test_gets_metadata(self, b2_bucket, b2_storage):
        b2_bucket.get_file_info_by_name.return_value.file_info = {
            "foo": "bar",
            "wu": "tang",
        }

        metadata = b2_storage.get_metadata("file.txt")

        assert metadata == {"foo": "bar", "wu": "tang"}
        b2_bucket.get_file_info_by_name.assert_called_once_with("file.txt")

    def test_raises_when_key_non_existent(self, b2_bucket, b2_storage):
        b2_bucket.download_file_by_name.side_effect = b2sdk.v2.exception.FileNotPresent

        with pytest.raises(FileNotFoundError):
            b2_storage.get("file.txt")

    def test_get_metadata_raises_when_key_non_existent(self, b2_bucket, b2_storage):
        b2_bucket.get_file_info_by_name.side_effect = b2sdk.v2.exception.FileNotPresent

        with pytest.raises(FileNotFoundError):
            b2_storage.get_metadata("file.txt")

    def test_gets_size(self, b2_bucket, b2_storage, mocker):
        b2_bucket.get_file_info_by_name.return_value = mocker.Mock(size=1234)

        assert b2_storage.get_size("file.txt") == 1234
        b2_bucket.get_file_info_by_name.assert_called_once_with("file.txt")

    def test_get_size_raises_when_key_non_existent(self, b2_bucket, b2_storage):
        b2_bucket.get_file_info_by_name.side_effect = b2sdk.v2.exception.FileNotPresent

        with pytest.raises(FileNotFoundError):
            b2_storage.get_size("file.txt")

    def test_stores_file(self, upload_file, b2_bucket, b2_storage):
        filename = upload_file()

        b2_storage.store("foo/bar.txt", filename)

        b2_bucket.upload_local_file.assert_called_once_with(
            local_file=filename, file_name="foo/bar.txt", file_infos=None
        )


class TestS3FileStorage:
    @pytest.fixture
    def s3_bucket(self, mocker):
        """A boto3 Bucket resource, which can't be autospec'd: introspecting one
        loads it lazily, which reaches for the network."""
        return mocker.Mock()

    @pytest.fixture
    def s3_storage(self, s3_bucket):
        return S3FileStorage(s3_bucket)

    def test_verify_service(self):
        assert verifyClass(IFileStorage, S3FileStorage)

    def test_basic_init(self, s3_bucket):
        storage = S3FileStorage(s3_bucket)
        assert storage.bucket is s3_bucket

    def test_create_service(self, service_request):
        session = boto3.session.Session(
            aws_access_key_id="foo", aws_secret_access_key="bar"
        )
        request = service_request({"files.bucket": "froblob"}, session)

        storage = S3FileStorage.create_service(None, request)

        request.find_service.assert_called_once_with(name="aws.session")
        assert storage.bucket.name == "froblob"

    def test_gets_file(self, s3_bucket, s3_storage):
        s3_bucket.Object.return_value.get.return_value = {
            "Body": io.BytesIO(b"my contents")
        }

        file_object = s3_storage.get("file.txt")

        assert file_object.read() == b"my contents"
        s3_bucket.Object.assert_called_once_with("file.txt")

    def test_gets_metadata(self, s3_bucket, s3_storage):
        s3_bucket.Object.return_value.metadata = {"foo": "bar", "wu": "tang"}

        metadata = s3_storage.get_metadata("file.txt")

        assert metadata == {"foo": "bar", "wu": "tang"}
        s3_bucket.Object.assert_called_once_with("file.txt")

    def test_raises_when_key_non_existent(self, s3_bucket, s3_storage):
        s3_bucket.Object.return_value.get.side_effect = botocore.exceptions.ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "No Key!"}}, "some operation"
        )

        with pytest.raises(FileNotFoundError):
            s3_storage.get("file.txt")

        s3_bucket.Object.assert_called_once_with("file.txt")

    def test_get_metadata_raises_when_key_non_existent(self, s3_bucket, s3_storage):
        s3_bucket.Object.side_effect = botocore.exceptions.ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "No Key!"}}, "some operation"
        )

        with pytest.raises(FileNotFoundError):
            s3_storage.get_metadata("file.txt")

    def test_passes_up_error_when_not_no_such_key(self, s3_bucket, s3_storage):
        s3_bucket.Object.return_value.get.side_effect = botocore.exceptions.ClientError(
            {"Error": {"Code": "SomeOtherError", "Message": "Who Knows!"}},
            "some operation",
        )

        with pytest.raises(botocore.exceptions.ClientError):
            s3_storage.get("file.txt")

    def test_get_metadata_passes_up_error_when_not_no_such_key(
        self, s3_bucket, s3_storage
    ):
        s3_bucket.Object.side_effect = botocore.exceptions.ClientError(
            {"Error": {"Code": "SomeOtherError", "Message": "Who Knows!"}},
            "some operation",
        )

        with pytest.raises(botocore.exceptions.ClientError):
            s3_storage.get_metadata("file.txt")

    def test_gets_size(self, s3_bucket, s3_storage, mocker):
        s3_bucket.Object.return_value = mocker.Mock(content_length=1234)

        assert s3_storage.get_size("file.txt") == 1234
        s3_bucket.Object.assert_called_once_with("file.txt")

    def test_get_size_raises_when_key_non_existent(self, s3_bucket, s3_storage):
        s3_bucket.Object.side_effect = botocore.exceptions.ClientError(
            {"ResponseMetadata": {"HTTPStatusCode": 404}}, "some operation"
        )

        with pytest.raises(FileNotFoundError):
            s3_storage.get_size("file.txt")

    def test_get_size_passes_up_error_when_not_no_such_key(self, s3_bucket, s3_storage):
        s3_bucket.Object.side_effect = botocore.exceptions.ClientError(
            {"ResponseMetadata": {"HTTPStatusCode": 666}}, "some operation"
        )

        with pytest.raises(botocore.exceptions.ClientError):
            s3_storage.get_size("file.txt")

    def test_stores_file(self, upload_file, s3_bucket, s3_storage):
        filename = upload_file()

        s3_storage.store("foo/bar.txt", filename)

        s3_bucket.upload_file.assert_called_once_with(
            filename, "foo/bar.txt", ExtraArgs={}
        )

    def test_stores_two_files(self, upload_file, s3_bucket, s3_storage, mocker):
        filename1 = upload_file(b"First Test File!", "testfile1.txt")
        filename2 = upload_file(b"Second Test File!", "testfile2.txt")

        s3_storage.store("foo/first.txt", filename1)
        s3_storage.store("foo/second.txt", filename2)

        assert s3_bucket.upload_file.call_args_list == [
            mocker.call(filename1, "foo/first.txt", ExtraArgs={}),
            mocker.call(filename2, "foo/second.txt", ExtraArgs={}),
        ]

    def test_stores_metadata(self, upload_file, s3_bucket, s3_storage):
        filename = upload_file()

        s3_storage.store("foo/bar.txt", filename, meta={"foo": "bar"})

        s3_bucket.upload_file.assert_called_once_with(
            filename, "foo/bar.txt", ExtraArgs={"Metadata": {"foo": "bar"}}
        )

    @pytest.mark.parametrize(
        ("prefix", "expected"),
        [("packages/", "packages/ab/file.txt"), (None, "ab/file.txt")],
    )
    def test_hashed_path(self, s3_bucket, prefix, expected):
        s3_bucket.Object.return_value.get.return_value = {
            "Body": io.BytesIO(b"my contents")
        }
        storage = S3FileStorage(s3_bucket, prefix=prefix)

        file_object = storage.get("ab/file.txt")

        assert file_object.read() == b"my contents"
        s3_bucket.Object.assert_called_once_with(expected)


class TestS3ArchiveFileStorage:
    def test_verify_service(self):
        assert verifyClass(IFileStorage, S3ArchiveFileStorage)

    def test_create_service(self, service_request):
        session = boto3.session.Session(
            aws_access_key_id="foo", aws_secret_access_key="bar"
        )
        request = service_request({"archive_files.bucket": "froblob"}, session)

        storage = S3ArchiveFileStorage.create_service(None, request)

        request.find_service.assert_called_once_with(name="aws.session")
        assert storage.bucket.name == "froblob"


class TestGCSFileStorage:
    def test_verify_service(self):
        assert verifyClass(IFileStorage, GCSFileStorage)

    def test_basic_init(self, gcs_bucket):
        storage = GCSFileStorage(gcs_bucket)
        assert storage.bucket is gcs_bucket

    def test_create_service(self, mocker, service_request):
        gcs_client = mocker.create_autospec(google.cloud.storage.Client, instance=True)
        request = service_request({"files.bucket": "froblob"}, gcs_client)

        GCSFileStorage.create_service(None, request)

        request.find_service.assert_called_once_with(name="gcloud.gcs")
        gcs_client.get_bucket.assert_called_once_with("froblob")

    def test_gets_file_raises(self, gcs_bucket):
        storage = GCSFileStorage(gcs_bucket)

        with pytest.raises(NotImplementedError):
            storage.get("file.txt")

    def test_get_metadata_raises(self, gcs_bucket):
        storage = GCSFileStorage(gcs_bucket)

        with pytest.raises(NotImplementedError):
            storage.get_metadata("file.txt")

    def test_get_size_raises(self, gcs_bucket):
        storage = GCSFileStorage(gcs_bucket)

        with pytest.raises(NotImplementedError):
            storage.get_size("file.txt")

    def test_stores_file(self, upload_file, gcs_bucket, gcs_blob):
        filename = upload_file()

        storage = GCSFileStorage(gcs_bucket)
        storage.store("foo/bar.txt", filename)

        gcs_bucket.blob.assert_called_once_with("foo/bar.txt")
        gcs_blob.upload_from_filename.assert_called_once_with(filename)

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("xx/foo/bar.txt", "myprefix/xx/foo/bar.txt"),
            ("foo/bar.txt", "myprefix/foo/bar.txt"),
        ],
    )
    def test_stores_file_with_prefix(
        self, upload_file, gcs_bucket, gcs_blob, path, expected
    ):
        filename = upload_file()

        storage = GCSFileStorage(gcs_bucket, prefix="myprefix/")
        storage.store(path, filename)

        gcs_bucket.blob.assert_called_once_with(expected)
        gcs_blob.upload_from_filename.assert_called_once_with(filename)

    def test_stores_two_files(self, upload_file, gcs_bucket, gcs_blob, mocker):
        filename1 = upload_file(b"First Test File!", "testfile1.txt")
        filename2 = upload_file(b"Second Test File!", "testfile2.txt")

        storage = GCSFileStorage(gcs_bucket)
        storage.store("foo/first.txt", filename1)
        storage.store("foo/second.txt", filename2)

        assert gcs_bucket.blob.call_args_list == [
            mocker.call("foo/first.txt"),
            mocker.call("foo/second.txt"),
        ]
        assert gcs_blob.upload_from_filename.call_args_list == [
            mocker.call(filename1),
            mocker.call(filename2),
        ]

    def test_stores_metadata(self, upload_file, gcs_bucket, gcs_blob):
        filename = upload_file()

        storage = GCSFileStorage(gcs_bucket)
        meta = {"foo": "bar"}
        storage.store("foo/bar.txt", filename, meta=meta)

        assert gcs_blob.metadata == meta

    def test_skips_upload_if_file_exists(
        self, upload_file, gcs_bucket, gcs_blob, mocker
    ):
        filename = upload_file()

        gcs_blob.exists.return_value = True
        capture_message = mocker.patch.object(
            warehouse.packaging.services.sentry_sdk, "capture_message", autospec=True
        )

        storage = GCSFileStorage(gcs_bucket)
        storage.store("foo/bar.txt", filename)

        gcs_bucket.blob.assert_called_once_with("foo/bar.txt")
        gcs_blob.upload_from_filename.assert_not_called()
        capture_message.assert_called_once_with(
            f"Skipped uploading duplicate file: {filename}"
        )


class TestS3DocsStorage:
    @pytest.fixture
    def s3_client(self, mocker):
        """Autospec a real S3 client, so the method names are checked. Unlike a
        Bucket resource, a client introspects without reaching the network."""
        session = boto3.session.Session(
            aws_access_key_id="foo",
            aws_secret_access_key="bar",
            region_name="us-east-1",
        )
        return mocker.create_autospec(session.client("s3"), instance=True)

    def test_verify_service(self):
        assert verifyClass(IDocsStorage, S3DocsStorage)

    def test_create_service(self, service_request):
        session = boto3.session.Session(
            aws_access_key_id="foo", aws_secret_access_key="bar"
        )
        request = service_request({"docs.bucket": "froblob"}, session)

        storage = S3DocsStorage.create_service(None, request)

        request.find_service.assert_called_once_with(name="aws.session")
        assert storage.bucket_name == "froblob"

    @pytest.mark.parametrize("file_count", [66, 100])
    def test_delete_by_prefix(self, s3_client, file_count):
        s3_client.list_objects_v2.return_value = {
            "Contents": [{"Key": f"foo/{i}.html"} for i in range(file_count)]
        }
        storage = S3DocsStorage(s3_client, "bucket-name")

        storage.remove_by_prefix("foo")

        s3_client.list_objects_v2.assert_called_once_with(
            Bucket="bucket-name", Prefix="foo"
        )
        s3_client.delete_objects.assert_called_once_with(
            Bucket="bucket-name",
            Delete={"Objects": [{"Key": f"foo/{i}.html"} for i in range(file_count)]},
        )

    def test_delete_by_prefix_more_files(self, s3_client, mocker):
        s3_client.list_objects_v2.return_value = {
            "Contents": [{"Key": f"foo/{i}.html"} for i in range(150)]
        }
        storage = S3DocsStorage(s3_client, "bucket-name")

        storage.remove_by_prefix("foo")

        s3_client.list_objects_v2.assert_called_once_with(
            Bucket="bucket-name", Prefix="foo"
        )
        assert s3_client.delete_objects.call_args_list == [
            mocker.call(
                Bucket="bucket-name",
                Delete={"Objects": [{"Key": f"foo/{i}.html"} for i in range(100)]},
            ),
            mocker.call(
                Bucket="bucket-name",
                Delete={"Objects": [{"Key": f"foo/{i}.html"} for i in range(100, 150)]},
            ),
        ]

    def test_delete_by_prefix_with_storage_prefix(self, s3_client, mocker):
        s3_client.list_objects_v2.return_value = {
            "Contents": [{"Key": f"docs/foo/{i}.html"} for i in range(150)]
        }
        storage = S3DocsStorage(s3_client, "bucket-name", prefix="docs")

        storage.remove_by_prefix("foo")

        s3_client.list_objects_v2.assert_called_once_with(
            Bucket="bucket-name", Prefix="docs/foo"
        )
        assert s3_client.delete_objects.call_args_list == [
            mocker.call(
                Bucket="bucket-name",
                Delete={"Objects": [{"Key": f"docs/foo/{i}.html"} for i in range(100)]},
            ),
            mocker.call(
                Bucket="bucket-name",
                Delete={
                    "Objects": [{"Key": f"docs/foo/{i}.html"} for i in range(100, 150)]
                },
            ),
        ]


class TestGCSSimpleStorage:
    def test_verify_service(self):
        assert verifyClass(ISimpleStorage, GCSSimpleStorage)

    def test_basic_init(self, gcs_bucket):
        storage = GCSSimpleStorage(gcs_bucket)
        assert storage.bucket is gcs_bucket

    def test_create_service(self, mocker, service_request):
        gcs_client = mocker.create_autospec(google.cloud.storage.Client, instance=True)
        request = service_request({"simple.bucket": "froblob"}, gcs_client)

        GCSSimpleStorage.create_service(None, request)

        request.find_service.assert_called_once_with(name="gcloud.gcs")
        gcs_client.get_bucket.assert_called_once_with("froblob")

    def test_gets_file_raises(self, gcs_bucket):
        storage = GCSSimpleStorage(gcs_bucket)

        with pytest.raises(NotImplementedError):
            storage.get("file.txt")

    def test_stores_file(self, upload_file, gcs_bucket, gcs_blob):
        filename = upload_file()

        storage = GCSSimpleStorage(gcs_bucket)
        storage.store("foo/bar.txt", filename)

        gcs_bucket.blob.assert_called_once_with("foo/bar.txt")
        gcs_blob.upload_from_filename.assert_called_once_with(filename)

    def test_stores_two_files(self, upload_file, gcs_bucket, gcs_blob, mocker):
        filename1 = upload_file(b"First Test File!", "testfile1.txt")
        filename2 = upload_file(b"Second Test File!", "testfile2.txt")

        storage = GCSSimpleStorage(gcs_bucket)
        storage.store("foo/first.txt", filename1)
        storage.store("foo/second.txt", filename2)

        assert gcs_bucket.blob.call_args_list == [
            mocker.call("foo/first.txt"),
            mocker.call("foo/second.txt"),
        ]
        assert gcs_blob.upload_from_filename.call_args_list == [
            mocker.call(filename1),
            mocker.call(filename2),
        ]

    def test_stores_metadata(self, upload_file, gcs_bucket, gcs_blob):
        filename = upload_file()

        storage = GCSSimpleStorage(gcs_bucket)
        meta = {"foo": "bar"}
        storage.store("foo/bar.txt", filename, meta=meta)

        assert gcs_blob.metadata == meta


class TestGenericLocalBlobStorage:
    def test_notimplementederror(self, mocker):
        with pytest.raises(NotImplementedError):
            GenericLocalBlobStorage.create_service(
                mocker.sentinel.context, mocker.sentinel.request
            )


class TestProjectService:
    def test_verify_service(self):
        assert verifyClass(IProjectService, ProjectService)

    @pytest.mark.parametrize("name", ["", ".,;", "_z", "İnspect"])
    def test_check_project_name_invalid(self, mocker, name):
        service = ProjectService(session=mocker.sentinel.session)

        with pytest.raises(ProjectNameUnavailableInvalidError):
            service.check_project_name(name)

    @pytest.mark.parametrize("name", ["uu", "cgi", "nis", "mailcap"])
    def test_check_project_name_stdlib(self, mocker, name):
        service = ProjectService(session=mocker.sentinel.session)

        with pytest.raises(ProjectNameUnavailableStdlibError):
            service.check_project_name(name)

    def test_check_project_test_new_disallowed(self, db_request, mocker):
        admin_flag = (
            db_request.db.query(AdminFlag)
            .filter(
                AdminFlag.id == AdminFlagValue.DISALLOW_NEW_PROJECT_REGISTRATION.value
            )
            .first()
        )
        admin_flag.enabled = True

        # help_url is added by a request extension, so DummyRequest lacks it
        db_request.help_url = mocker.Mock(return_value="/the/help/url/")

        service = ProjectService(session=db_request.db)

        with pytest.raises(HTTPForbidden) as exc:
            service.create_project(
                "foo", mocker.sentinel.creator, db_request, ratelimited=False
            )

        resp = exc.value
        assert resp.status_code == 403
        assert resp.detail == (
            "New project registration temporarily disabled. See "
            "/the/help/url/ for more information."
        )

    @pytest.mark.parametrize(
        ("enforce", "limiter_method", "limiter_name", "keyed_on_creator"),
        [
            (ProjectService._check_ratelimits, "test", "project.create.ip", False),
            (ProjectService._check_ratelimits, "test", "project.create.user", True),
            (ProjectService._hit_ratelimits, "hit", "project.create.user", True),
            (ProjectService._hit_ratelimits, "hit", "project.create.ip", False),
        ],
        ids=["check-ip", "check-user", "hit-user", "hit-ip"],
    )
    def test_ratelimit_exceeded_raises_with_correct_reset_hint(
        self,
        project_service,
        db_request,
        ratelimit_service,
        mocker,
        enforce,
        limiter_method,
        limiter_name,
        keyed_on_creator,
    ):
        """A limiter reporting its threshold is reached refuses the creation.

        Both the optimistic ``_check_ratelimits`` gate (via ``test``) and the
        enforcing ``_hit_ratelimits`` gate (via ``hit``) raise, and the reset
        hint is keyed on the identifier that tripped the limit: the creator's id
        for the user limit, the request IP for the IP limit.
        """
        creator = UserFactory.create()
        # Trip just the limiter under test; the other auto-creates and passes.
        project_service.ratelimiters[limiter_name] = ratelimit_service
        mocker.patch.object(ratelimit_service, limiter_method, return_value=False)

        identity = project_service._identity_limiter(creator, None)

        with pytest.raises(TooManyProjectsCreated):
            enforce(project_service, db_request, identity)

        expected = creator.id if keyed_on_creator else db_request.remote_addr
        ratelimit_service.resets_in.assert_called_once_with(expected)

    def test_hit_ratelimits_skips_ip_limiter_without_remote_addr(
        self, project_service, db_request, ratelimit_service
    ):
        """With no resolvable client IP the IP limiter is left untouched.

        This mirrors the guard already present in ``_check_ratelimits``.
        """
        creator = UserFactory.create()
        db_request.remote_addr = None
        project_service.ratelimiters["project.create.ip"] = ratelimit_service

        project_service._hit_ratelimits(
            db_request, project_service._identity_limiter(creator, None)
        )

        ratelimit_service.hit.assert_not_called()

    def test_create_project_rejects_when_hit_exceeds_limit(
        self, project_service, db_request, ratelimit_service, mocker
    ):
        """The atomic ``hit`` enforces the limit even when ``test`` passed.

        A burst of concurrent uploads can each clear the optimistic ``test``
        check before any of them records a hit, so the per-request ``hit`` is
        what actually caps creation: a request that pushes the counter past the
        limit is rejected, rolling back the project just created.
        """
        creator = UserFactory.create()
        project_service.ratelimiters["project.create.user"] = ratelimit_service
        mocker.patch.object(ratelimit_service, "hit", return_value=False)

        with pytest.raises(TooManyProjectsCreated):
            project_service.create_project("some-new-project", creator, db_request)

    def test_check_ratelimits_records_rate_limit_headers(
        self, project_service, db_request, ratelimit_service, mocker
    ):
        """`_check_ratelimits` records a snapshot per limiter so the egress
        tween can emit RateLimit / RateLimit-Policy headers on the response.
        """
        creator = UserFactory.create()
        stats = [
            WindowStats(
                amount=4, window_seconds=86400, remaining=3, resets_in_seconds=0
            )
        ]
        mocker.patch.object(ratelimit_service, "get_window_stats", return_value=stats)
        project_service.ratelimiters["project.create.user"] = ratelimit_service
        project_service.ratelimiters["project.create.ip"] = ratelimit_service

        project_service._check_ratelimits(
            db_request, project_service._identity_limiter(creator, None)
        )

        # Keyed on the request IP and the creator's id, in that order.
        assert ratelimit_service.get_window_stats.call_args_list == [
            mocker.call(db_request.remote_addr),
            mocker.call(creator.id),
        ]
        snapshots = db_request._rate_limit_snapshots
        assert [(s.name, s.partition_key, s.stats) for s in snapshots] == [
            ("project.create.ip", "ip", stats),
            ("project.create.user", "user", stats),
        ]

    def test_identity_limiter_defaults_to_user(
        self, project_service, ratelimit_service, mocker
    ):
        creator = UserFactory.create()
        project_service.ratelimiters["project.create.user"] = ratelimit_service
        override = mocker.spy(ratelimit_service, "override")

        identity = project_service._identity_limiter(creator, None)

        assert identity.limiter is ratelimit_service
        assert identity.identifier == creator.id
        assert identity.partition_key == "user"
        # Nothing stored, so the configured default is used unchanged.
        override.assert_called_once_with(None)

    def test_identity_limiter_applies_user_override(
        self, project_service, ratelimit_service, mocker
    ):
        """An override is applied through the default limiter's `.override()`."""
        creator = UserFactory.create(
            project_create_ratelimit_count=5,
            project_create_ratelimit_period=RateLimitPeriod.Hour,
        )
        project_service.ratelimiters["project.create.user"] = ratelimit_service
        override = mocker.spy(ratelimit_service, "override")

        identity = project_service._identity_limiter(creator, None)

        override.assert_called_once_with("5 per hour")
        assert identity.identifier == creator.id
        assert identity.partition_key == "user"

    def test_identity_limiter_uses_organization_when_scoped(
        self, project_service, ratelimit_service, mocker
    ):
        """Creation inside an org is keyed on the org, not the creator."""
        creator = UserFactory.create()
        organization = OrganizationFactory.create(project_create_ratelimit_count=None)
        project_service.ratelimiters["project.create.organization"] = ratelimit_service
        override = mocker.spy(ratelimit_service, "override")

        identity = project_service._identity_limiter(creator, organization.id)

        assert identity.limiter is ratelimit_service
        assert identity.identifier == organization.id
        assert identity.partition_key == "organization"
        override.assert_called_once_with(None)

    @pytest.mark.parametrize(
        ("period", "expected"),
        [
            (RateLimitPeriod.Hour, "200 per hour"),
            (RateLimitPeriod.Day, "200 per day"),
            (RateLimitPeriod.Month, "200 per month"),
        ],
    )
    def test_identity_limiter_applies_organization_override(
        self, project_service, ratelimit_service, mocker, period, expected
    ):
        organization = OrganizationFactory.create(
            project_create_ratelimit_count=200,
            project_create_ratelimit_period=period,
        )
        project_service.ratelimiters["project.create.organization"] = ratelimit_service
        override = mocker.spy(ratelimit_service, "override")

        identity = project_service._identity_limiter(
            UserFactory.create(), organization.id
        )

        override.assert_called_once_with(expected)
        assert identity.identifier == organization.id

    @pytest.mark.parametrize(
        ("enforce", "limiter_method"),
        [
            (ProjectService._check_ratelimits, "test"),
            (ProjectService._hit_ratelimits, "hit"),
        ],
        ids=["check", "hit"],
    )
    def test_organization_ratelimit_exceeded_reports_the_organization_partition(
        self,
        project_service,
        db_request,
        ratelimit_service,
        metrics,
        mocker,
        enforce,
        limiter_method,
    ):
        """The metric tag and reset hint name the bucket that filled up."""
        organization = OrganizationFactory.create()
        project_service.ratelimiters["project.create.organization"] = ratelimit_service
        identity = project_service._identity_limiter(
            UserFactory.create(), organization.id
        )
        mocker.patch.object(ratelimit_service, limiter_method, return_value=False)

        with pytest.raises(TooManyProjectsCreated):
            enforce(project_service, db_request, identity)

        ratelimit_service.resets_in.assert_called_once_with(organization.id)
        metrics.increment.assert_any_call(
            "warehouse.project.create.ratelimited",
            tags=["ratelimiter:organization"],
        )

    def test_check_ratelimits_for_organization_does_not_consult_user_limiter(
        self, project_service, db_request, ratelimit_service
    ):
        organization = OrganizationFactory.create()
        project_service.ratelimiters["project.create.user"] = ratelimit_service
        project_service.ratelimiters["project.create.organization"] = DummyRateLimiter()
        identity = project_service._identity_limiter(
            UserFactory.create(), organization.id
        )

        project_service._check_ratelimits(db_request, identity)

        ratelimit_service.test.assert_not_called()

    def test_check_ratelimits_for_organization_still_checks_ip_limiter(
        self, project_service, db_request, ratelimit_service, mocker
    ):
        """The IP limiter still applies when the org limiter replaces the user one."""
        organization = OrganizationFactory.create()
        project_service.ratelimiters["project.create.ip"] = ratelimit_service
        project_service.ratelimiters["project.create.organization"] = DummyRateLimiter()
        identity = project_service._identity_limiter(
            UserFactory.create(), organization.id
        )
        mocker.patch.object(ratelimit_service, "test", return_value=False)

        with pytest.raises(TooManyProjectsCreated):
            project_service._check_ratelimits(db_request, identity)

        ratelimit_service.resets_in.assert_called_once_with(db_request.remote_addr)

    def test_create_project_resolves_the_identity_limiter_once(
        self, project_service, db_request, mocker
    ):
        """One resolved limiter is shared, so a create does one org lookup."""
        organization = OrganizationFactory.create()
        project_service.ratelimiters["project.create.organization"] = DummyRateLimiter()
        resolve = mocker.spy(project_service, "_identity_limiter")

        project_service.create_project(
            "some-new-project",
            UserFactory.create(),
            db_request,
            creator_is_owner=False,
            organization_id=organization.id,
        )

        assert resolve.call_count == 1

    def test_create_project_for_organization_rejects_when_hit_exceeds_limit(
        self, project_service, db_request, ratelimit_service, mocker
    ):
        creator = UserFactory.create()
        organization = OrganizationFactory.create()
        project_service.ratelimiters["project.create.organization"] = ratelimit_service
        mocker.patch.object(ratelimit_service, "hit", return_value=False)

        with pytest.raises(TooManyProjectsCreated):
            project_service.create_project(
                "some-new-project",
                creator,
                db_request,
                creator_is_owner=False,
                organization_id=organization.id,
            )

    def test_create_project_skips_ratelimits_when_not_ratelimited(
        self, project_service, db_request, ratelimit_service, mocker
    ):
        """`ratelimited=False` resolves no limiter at all."""
        organization = OrganizationFactory.create()
        project_service.ratelimiters["project.create.organization"] = ratelimit_service
        resolve = mocker.spy(project_service, "_identity_limiter")

        project_service.create_project(
            "some-new-project",
            UserFactory.create(),
            db_request,
            creator_is_owner=False,
            ratelimited=False,
            organization_id=organization.id,
        )

        resolve.assert_not_called()
        ratelimit_service.test.assert_not_called()
        ratelimit_service.hit.assert_not_called()

    def test_create_project_skips_owner_role_and_org_link_when_neither_applies(
        self, project_service, db_request
    ):
        """`creator_is_owner=False` with no org gets neither a Role nor a link."""
        creator = UserFactory.create()

        project = project_service.create_project(
            "some-new-project",
            creator,
            db_request,
            creator_is_owner=False,
        )

        assert db_request.db.query(Role).filter_by(project_id=project.id).count() == 0
        assert (
            db_request.db.query(OrganizationProject)
            .filter_by(project_id=project.id)
            .count()
            == 0
        )

    def test_create_project_links_to_organization_by_default(
        self, project_service, db_request
    ):
        creator = UserFactory.create()
        organization = OrganizationFactory.create()

        project = project_service.create_project(
            "some-new-project",
            creator,
            db_request,
            creator_is_owner=False,
            organization_id=organization.id,
        )

        assert (
            db_request.db.query(OrganizationProject)
            .filter_by(organization_id=organization.id, project_id=project.id)
            .count()
            == 1
        )

    def test_create_project_flags_organization_dirty_for_cache_purge(
        self, app_config, project_service, db_request
    ):
        """The OIDC auto-create path never calls
        IOrganizationService.add_organization_project, so create_project must
        purge the org itself."""
        creator = UserFactory.create()
        organization = OrganizationFactory.create()
        db_request.db.flush()
        db_request.db.info.pop("warehouse.cache.origin.purges", None)

        project_service.create_project(
            "some-new-project",
            creator,
            db_request,
            creator_is_owner=False,
            organization_id=organization.id,
        )
        db_request.db.flush()

        purges = db_request.db.info.get("warehouse.cache.origin.purges", set())
        assert f"org/{organization.normalized_name}" in purges

    def test_check_project_name_already_exists(self, db_session):
        service = ProjectService(session=db_session)
        project = ProjectFactory.create(name="foo")

        with pytest.raises(ProjectNameUnavailableExistingError) as exc:
            service.check_project_name("foo")
        assert exc.value.existing_project == project

        with pytest.raises(ProjectNameUnavailableExistingError):
            service.check_project_name("Foo")

    def test_check_project_name_prohibited(self, db_session):
        service = ProjectService(session=db_session)
        ProhibitedProjectFactory.create(name="foo")

        with pytest.raises(ProjectNameUnavailableProhibitedError):
            service.check_project_name("foo")

        with pytest.raises(ProjectNameUnavailableProhibitedError):
            service.check_project_name("Foo")

    def test_check_project_name_too_similar(self, db_session):
        service = ProjectService(session=db_session)
        ProjectFactory.create(name="f00")

        with pytest.raises(ProjectNameUnavailableSimilarError):
            service.check_project_name("foo")

    def test_check_project_name_too_similar_multiple_existing(self, db_session):
        service = ProjectService(session=db_session)
        project1 = ProjectFactory.create(name="f00")
        project2 = ProjectFactory.create(name="f0o")

        with pytest.raises(ProjectNameUnavailableSimilarError) as exc:
            service.check_project_name("foo")
        assert exc.value.similar_project_name in (project1.name, project2.name)

    def test_create_project_enqueues_typo_check(self, db_request):
        """Typo-squatting detection is handed off to a post-commit task, so it
        never runs for a project creation that ends up rolled back."""
        creator = UserFactory.create()
        service = ProjectService(session=db_request.db)

        project = service.create_project(
            "numpi", creator, db_request, ratelimited=False
        )

        assert project.name == "numpi"
        db_request.task.assert_called_once_with(typo_check_project_name)
        db_request._task_stub.delay.assert_called_once_with(project.id)

    def test_check_project_name_ok(self, db_session):
        service = ProjectService(session=db_session)

        # Should not raise any exception
        service.check_project_name("foo")


def test_project_service_factory(db_request, ratelimit_service, mocker):
    service = project_service_factory(mocker.sentinel.context, db_request)

    assert service.db is db_request.db
    # The factory resolves all three rate limiters from the registry by name.
    assert service.ratelimiters["project.create.user"] is ratelimit_service
    assert service.ratelimiters["project.create.ip"] is ratelimit_service
    assert service.ratelimiters["project.create.organization"] is ratelimit_service
