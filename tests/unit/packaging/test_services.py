# SPDX-License-Identifier: Apache-2.0

import hashlib
import io
import os.path

import b2sdk.v2.exception
import boto3.session
import botocore.exceptions
import pretend
import pytest

from pyramid.httpexceptions import HTTPForbidden
from zope.interface.verify import verifyClass

import warehouse.packaging.services

from warehouse.admin.flags import AdminFlag, AdminFlagValue
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
    ProjectNameUnavailableTypoSquattingError,
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
from warehouse.rate_limiting import DummyRateLimiter
from warehouse.rate_limiting.interfaces import WindowStats

from ...common.db.accounts import UserFactory
from ...common.db.organizations import OrganizationFactory
from ...common.db.packaging import ProhibitedProjectFactory, ProjectFactory


class TestLocalFileStorage:
    def test_verify_service(self):
        assert verifyClass(IFileStorage, LocalFileStorage)

    def test_basic_init(self):
        storage = LocalFileStorage("/foo/bar/")
        assert storage.base == "/foo/bar/"

    def test_create_service(self):
        request = pretend.stub(
            registry=pretend.stub(settings={"files.path": "/the/one/two/"})
        )
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

    def test_stores_file(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        storage_dir = str(tmpdir.join("storage"))
        storage = LocalFileStorage(storage_dir)
        storage.store("foo/bar.txt", filename)

        with open(os.path.join(storage_dir, "foo/bar.txt"), "rb") as fp:
            assert fp.read() == b"Test File!"

    def test_stores_and_gets_metadata(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        storage_dir = str(tmpdir.join("storage"))
        storage = LocalFileStorage(storage_dir)
        storage.store("foo/bar.txt", filename, meta={"foo": "bar", "wu": "tang"})

        with open(os.path.join(storage_dir, "foo/bar.txt"), "rb") as fp:
            assert fp.read() == b"Test File!"
        with open(os.path.join(storage_dir, "foo/bar.txt.meta"), "rb") as fp:
            assert fp.read() == b'{"foo": "bar", "wu": "tang"}'

        assert storage.get_metadata("foo/bar.txt") == {"foo": "bar", "wu": "tang"}

    def test_gets_metadata(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        storage_dir = str(tmpdir.join("storage"))
        storage = LocalFileStorage(storage_dir)
        storage.store("foo/bar.txt", filename)

        assert (
            storage.get_checksum("foo/bar.txt")
            == hashlib.md5(b"Test File!").hexdigest()
        )

    def test_stores_two_files(self, tmpdir):
        filename1 = str(tmpdir.join("testfile1.txt"))
        with open(filename1, "wb") as fp:
            fp.write(b"First Test File!")

        filename2 = str(tmpdir.join("testfile2.txt"))
        with open(filename2, "wb") as fp:
            fp.write(b"Second Test File!")

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

    def test_create_service(self):
        request = pretend.stub(
            registry=pretend.stub(settings={"archive_files.path": "/the/one/two/"})
        )
        storage = LocalArchiveFileStorage.create_service(None, request)
        assert storage.base == "/the/one/two/"


class TestLocalDocsStorage:
    def test_verify_service(self):
        assert verifyClass(IDocsStorage, LocalDocsStorage)

    def test_create_service(self):
        request = pretend.stub(
            registry=pretend.stub(settings={"docs.path": "/the/one/two/"})
        )
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

    def test_create_service(self):
        request = pretend.stub(
            registry=pretend.stub(settings={"simple.path": "/simple/one/two/"})
        )
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

    def test_stores_file(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        storage_dir = str(tmpdir.join("storage"))
        storage = LocalSimpleStorage(storage_dir)
        storage.store("foo/bar.txt", filename)

        with open(os.path.join(storage_dir, "foo/bar.txt"), "rb") as fp:
            assert fp.read() == b"Test File!"

    def test_stores_two_files(self, tmpdir):
        filename1 = str(tmpdir.join("testfile1.txt"))
        with open(filename1, "wb") as fp:
            fp.write(b"First Test File!")

        filename2 = str(tmpdir.join("testfile2.txt"))
        with open(filename2, "wb") as fp:
            fp.write(b"Second Test File!")

        storage_dir = str(tmpdir.join("storage"))
        storage = LocalSimpleStorage(storage_dir)
        storage.store("foo/first.txt", filename1)
        storage.store("foo/second.txt", filename2)

        with open(os.path.join(storage_dir, "foo/first.txt"), "rb") as fp:
            assert fp.read() == b"First Test File!"

        with open(os.path.join(storage_dir, "foo/second.txt"), "rb") as fp:
            assert fp.read() == b"Second Test File!"


class TestB2FileStorage:
    def test_verify_service(self):
        assert verifyClass(IFileStorage, B2FileStorage)

    def test_basic_init(self):
        bucket = pretend.stub()
        prefix = "segakcap"
        storage = B2FileStorage(bucket, prefix=prefix)
        assert storage.bucket is bucket
        assert storage.prefix == "segakcap"

    def test_create_service(self):
        bucket_stub = pretend.stub()
        mock_b2_api = pretend.stub(
            get_bucket_by_name=pretend.call_recorder(lambda bucket_name: bucket_stub)
        )

        request = pretend.stub(
            find_service=pretend.call_recorder(lambda name: mock_b2_api),
            registry=pretend.stub(settings={"files.bucket": "froblob"}),
        )
        storage = B2FileStorage.create_service(None, request)

        assert request.find_service.calls == [pretend.call(name="b2.api")]
        assert storage.bucket == bucket_stub
        assert mock_b2_api.get_bucket_by_name.calls == [pretend.call("froblob")]

    def test_gets_file(self):
        bucket_stub = pretend.stub(
            download_file_by_name=pretend.call_recorder(
                lambda path: pretend.stub(
                    save=lambda file_obj: file_obj.write(b"my contents")
                )
            )
        )
        mock_b2_api = pretend.stub(get_bucket_by_name=lambda bucket_name: bucket_stub)

        request = pretend.stub(
            find_service=pretend.call_recorder(lambda name: mock_b2_api),
            registry=pretend.stub(settings={"files.bucket": "froblob"}),
        )
        storage = B2FileStorage.create_service(None, request)

        file_object = storage.get("file.txt")

        assert file_object.read() == b"my contents"
        assert bucket_stub.download_file_by_name.calls == [pretend.call("file.txt")]

    def test_gets_metadata(self):
        bucket_stub = pretend.stub(
            get_file_info_by_name=pretend.call_recorder(
                lambda path: pretend.stub(file_info={"foo": "bar", "wu": "tang"})
            )
        )
        mock_b2_api = pretend.stub(get_bucket_by_name=lambda bucket_name: bucket_stub)

        request = pretend.stub(
            find_service=pretend.call_recorder(lambda name: mock_b2_api),
            registry=pretend.stub(settings={"files.bucket": "froblob"}),
        )
        storage = B2FileStorage.create_service(None, request)

        metadata = storage.get_metadata("file.txt")

        assert metadata == {"foo": "bar", "wu": "tang"}
        assert bucket_stub.get_file_info_by_name.calls == [pretend.call("file.txt")]

    def test_gets_checksum(self):
        bucket_stub = pretend.stub(
            get_file_info_by_name=pretend.call_recorder(
                lambda path: pretend.stub(id_="froblob"),
            ),
            get_file_info_by_id=pretend.call_recorder(
                lambda id_: pretend.stub(content_md5="deadbeef"),
            ),
        )
        mock_b2_api = pretend.stub(get_bucket_by_name=lambda bucket_name: bucket_stub)

        request = pretend.stub(
            find_service=pretend.call_recorder(lambda name: mock_b2_api),
            registry=pretend.stub(settings={"files.bucket": "froblob"}),
        )
        storage = B2FileStorage.create_service(None, request)

        checksum = storage.get_checksum("file.txt")

        assert checksum == "deadbeef"
        assert bucket_stub.get_file_info_by_name.calls == [pretend.call("file.txt")]

    def test_raises_when_key_non_existent(self):
        def raiser(path):
            raise b2sdk.v2.exception.FileNotPresent

        bucket_stub = pretend.stub(download_file_by_name=raiser)
        mock_b2_api = pretend.stub(get_bucket_by_name=lambda bucket_name: bucket_stub)

        request = pretend.stub(
            find_service=pretend.call_recorder(lambda name: mock_b2_api),
            registry=pretend.stub(settings={"files.bucket": "froblob"}),
        )
        storage = B2FileStorage.create_service(None, request)

        with pytest.raises(FileNotFoundError):
            storage.get("file.txt")

    def test_get_metadata_raises_when_key_non_existent(self):
        def raiser(path):
            raise b2sdk.v2.exception.FileNotPresent

        bucket_stub = pretend.stub(get_file_info_by_name=raiser)
        mock_b2_api = pretend.stub(get_bucket_by_name=lambda bucket_name: bucket_stub)

        request = pretend.stub(
            find_service=pretend.call_recorder(lambda name: mock_b2_api),
            registry=pretend.stub(settings={"files.bucket": "froblob"}),
        )
        storage = B2FileStorage.create_service(None, request)

        with pytest.raises(FileNotFoundError):
            storage.get_metadata("file.txt")

    def test_get_checksum_raises_when_key_non_existent(self):
        def raiser(path):
            raise b2sdk.v2.exception.FileNotPresent

        bucket_stub = pretend.stub(
            get_file_info_by_id=raiser, get_file_info_by_name=raiser
        )
        mock_b2_api = pretend.stub(get_bucket_by_name=lambda bucket_name: bucket_stub)

        request = pretend.stub(
            find_service=pretend.call_recorder(lambda name: mock_b2_api),
            registry=pretend.stub(settings={"files.bucket": "froblob"}),
        )
        storage = B2FileStorage.create_service(None, request)

        with pytest.raises(FileNotFoundError):
            storage.get_checksum("file.txt")

    def test_stores_file(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        bucket_stub = pretend.stub(
            upload_local_file=pretend.call_recorder(
                lambda local_file=None, file_name=None, file_infos=None: None
            )
        )
        mock_b2_api = pretend.stub(get_bucket_by_name=lambda bucket_name: bucket_stub)

        request = pretend.stub(
            find_service=pretend.call_recorder(lambda name: mock_b2_api),
            registry=pretend.stub(settings={"files.bucket": "froblob"}),
        )
        storage = B2FileStorage.create_service(None, request)

        storage.store("foo/bar.txt", filename)

        assert bucket_stub.upload_local_file.calls == [
            pretend.call(local_file=filename, file_name="foo/bar.txt", file_infos=None)
        ]


class TestS3FileStorage:
    def test_verify_service(self):
        assert verifyClass(IFileStorage, S3FileStorage)

    def test_basic_init(self):
        bucket = pretend.stub()
        storage = S3FileStorage(bucket)
        assert storage.bucket is bucket

    def test_create_service(self):
        session = boto3.session.Session(
            aws_access_key_id="foo", aws_secret_access_key="bar"
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda name: session),
            registry=pretend.stub(settings={"files.bucket": "froblob"}),
        )
        storage = S3FileStorage.create_service(None, request)

        assert request.find_service.calls == [pretend.call(name="aws.session")]
        assert storage.bucket.name == "froblob"

    def test_gets_file(self):
        s3key = pretend.stub(get=lambda: {"Body": io.BytesIO(b"my contents")})
        bucket = pretend.stub(Object=pretend.call_recorder(lambda path: s3key))
        storage = S3FileStorage(bucket)

        file_object = storage.get("file.txt")

        assert file_object.read() == b"my contents"
        assert bucket.Object.calls == [pretend.call("file.txt")]

    def test_gets_metadata(self):
        s3key = pretend.stub(metadata={"foo": "bar", "wu": "tang"})
        bucket = pretend.stub(Object=pretend.call_recorder(lambda path: s3key))
        storage = S3FileStorage(bucket)

        metadata = storage.get_metadata("file.txt")

        assert metadata == {"foo": "bar", "wu": "tang"}
        assert bucket.Object.calls == [pretend.call("file.txt")]

    def test_gets_checksum(self):
        s3key = pretend.stub(e_tag="deadbeef")
        bucket = pretend.stub(Object=pretend.call_recorder(lambda path: s3key))
        storage = S3FileStorage(bucket)

        checksum = storage.get_checksum("file.txt")

        assert checksum == "deadbeef"
        assert bucket.Object.calls == [pretend.call("file.txt")]

    def test_raises_when_key_non_existent(self):
        def raiser():
            raise botocore.exceptions.ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "No Key!"}}, "some operation"
            )

        s3key = pretend.stub(get=raiser)
        bucket = pretend.stub(Object=pretend.call_recorder(lambda path: s3key))
        storage = S3FileStorage(bucket)

        with pytest.raises(FileNotFoundError):
            storage.get("file.txt")

        assert bucket.Object.calls == [pretend.call("file.txt")]

    def test_get_metadata_raises_when_key_non_existent(self):
        def raiser(*a, **kw):
            raise botocore.exceptions.ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "No Key!"}}, "some operation"
            )

        bucket = pretend.stub(Object=raiser)
        storage = S3FileStorage(bucket)

        with pytest.raises(FileNotFoundError):
            storage.get_metadata("file.txt")

    def test_get_checksum_raises_when_key_non_existent(self):
        def raiser(*a, **kw):
            raise botocore.exceptions.ClientError(
                {"ResponseMetadata": {"HTTPStatusCode": 404}}, "some operation"
            )

        bucket = pretend.stub(Object=raiser)
        storage = S3FileStorage(bucket)

        with pytest.raises(FileNotFoundError):
            storage.get_checksum("file.txt")

    def test_passes_up_error_when_not_no_such_key(self):
        def raiser():
            raise botocore.exceptions.ClientError(
                {"Error": {"Code": "SomeOtherError", "Message": "Who Knows!"}},
                "some operation",
            )

        s3key = pretend.stub(get=raiser)
        bucket = pretend.stub(Object=pretend.call_recorder(lambda path: s3key))
        storage = S3FileStorage(bucket)

        with pytest.raises(botocore.exceptions.ClientError):
            storage.get("file.txt")

    def test_get_metadata_passes_up_error_when_not_no_such_key(self):
        def raiser(*a, **kw):
            raise botocore.exceptions.ClientError(
                {"Error": {"Code": "SomeOtherError", "Message": "Who Knows!"}},
                "some operation",
            )

        bucket = pretend.stub(Object=raiser)
        storage = S3FileStorage(bucket)

        with pytest.raises(botocore.exceptions.ClientError):
            storage.get_metadata("file.txt")

    def test_get_checksum_passes_up_error_when_not_no_such_key(self):
        def raiser(*a, **kw):
            raise botocore.exceptions.ClientError(
                {"ResponseMetadata": {"HTTPStatusCode": 666}},
                "some operation",
            )

        bucket = pretend.stub(Object=raiser)
        storage = S3FileStorage(bucket)

        with pytest.raises(botocore.exceptions.ClientError):
            storage.get_checksum("file.txt")

    def test_stores_file(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        bucket = pretend.stub(
            upload_file=pretend.call_recorder(
                lambda filename, key, ExtraArgs: None  # noqa: N803
            )
        )
        storage = S3FileStorage(bucket)
        storage.store("foo/bar.txt", filename)

        assert bucket.upload_file.calls == [
            pretend.call(filename, "foo/bar.txt", ExtraArgs={})
        ]

    def test_stores_two_files(self, tmpdir):
        filename1 = str(tmpdir.join("testfile1.txt"))
        with open(filename1, "wb") as fp:
            fp.write(b"First Test File!")

        filename2 = str(tmpdir.join("testfile2.txt"))
        with open(filename2, "wb") as fp:
            fp.write(b"Second Test File!")

        bucket = pretend.stub(
            upload_file=pretend.call_recorder(
                lambda filename, key, ExtraArgs: None  # noqa: N803
            )
        )
        storage = S3FileStorage(bucket)
        storage.store("foo/first.txt", filename1)
        storage.store("foo/second.txt", filename2)

        assert bucket.upload_file.calls == [
            pretend.call(filename1, "foo/first.txt", ExtraArgs={}),
            pretend.call(filename2, "foo/second.txt", ExtraArgs={}),
        ]

    def test_stores_metadata(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        bucket = pretend.stub(
            upload_file=pretend.call_recorder(
                lambda filename, key, ExtraArgs: None  # noqa: N803
            )
        )
        storage = S3FileStorage(bucket)
        storage.store("foo/bar.txt", filename, meta={"foo": "bar"})

        assert bucket.upload_file.calls == [
            pretend.call(
                filename, "foo/bar.txt", ExtraArgs={"Metadata": {"foo": "bar"}}
            )
        ]

    def test_hashed_path_with_prefix(self):
        s3key = pretend.stub(get=lambda: {"Body": io.BytesIO(b"my contents")})
        bucket = pretend.stub(Object=pretend.call_recorder(lambda path: s3key))
        storage = S3FileStorage(bucket, prefix="packages/")

        file_object = storage.get("ab/file.txt")

        assert file_object.read() == b"my contents"
        assert bucket.Object.calls == [pretend.call("packages/ab/file.txt")]

    def test_hashed_path_without_prefix(self):
        s3key = pretend.stub(get=lambda: {"Body": io.BytesIO(b"my contents")})
        bucket = pretend.stub(Object=pretend.call_recorder(lambda path: s3key))
        storage = S3FileStorage(bucket)

        file_object = storage.get("ab/file.txt")

        assert file_object.read() == b"my contents"
        assert bucket.Object.calls == [pretend.call("ab/file.txt")]


class TestS3ArchiveFileStorage:
    def test_verify_service(self):
        assert verifyClass(IFileStorage, S3ArchiveFileStorage)

    def test_create_service(self):
        session = boto3.session.Session(
            aws_access_key_id="foo", aws_secret_access_key="bar"
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda name: session),
            registry=pretend.stub(settings={"archive_files.bucket": "froblob"}),
        )
        storage = S3ArchiveFileStorage.create_service(None, request)

        assert request.find_service.calls == [pretend.call(name="aws.session")]
        assert storage.bucket.name == "froblob"


class TestGCSFileStorage:
    def test_verify_service(self):
        assert verifyClass(IFileStorage, GCSFileStorage)

    def test_basic_init(self):
        bucket = pretend.stub()
        storage = GCSFileStorage(bucket)
        assert storage.bucket is bucket

    def test_create_service(self):
        service = pretend.stub(
            get_bucket=pretend.call_recorder(lambda bucket_name: pretend.stub())
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda name: service),
            registry=pretend.stub(settings={"files.bucket": "froblob"}),
        )
        GCSFileStorage.create_service(None, request)

        assert request.find_service.calls == [pretend.call(name="gcloud.gcs")]
        assert service.get_bucket.calls == [pretend.call("froblob")]

    def test_gets_file_raises(self):
        storage = GCSFileStorage(pretend.stub())

        with pytest.raises(NotImplementedError):
            storage.get("file.txt")

    def test_get_metadata_raises(self):
        storage = GCSFileStorage(pretend.stub())

        with pytest.raises(NotImplementedError):
            storage.get_metadata("file.txt")

    def test_get_checksum_raises(self):
        storage = GCSFileStorage(pretend.stub())

        with pytest.raises(NotImplementedError):
            storage.get_checksum("file.txt")

    def test_stores_file(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        blob = pretend.stub(
            upload_from_filename=pretend.call_recorder(lambda file_path: None),
            exists=lambda: False,
        )
        bucket = pretend.stub(blob=pretend.call_recorder(lambda path: blob))
        storage = GCSFileStorage(bucket)
        storage.store("foo/bar.txt", filename)

        assert bucket.blob.calls == [pretend.call("foo/bar.txt")]
        assert blob.upload_from_filename.calls == [pretend.call(filename)]

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("xx/foo/bar.txt", "myprefix/xx/foo/bar.txt"),
            ("foo/bar.txt", "myprefix/foo/bar.txt"),
        ],
    )
    def test_stores_file_with_prefix(self, tmpdir, path, expected):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        blob = pretend.stub(
            upload_from_filename=pretend.call_recorder(lambda file_path: None),
            exists=lambda: False,
        )
        bucket = pretend.stub(blob=pretend.call_recorder(lambda path: blob))
        storage = GCSFileStorage(bucket, prefix="myprefix/")
        storage.store(path, filename)

        assert bucket.blob.calls == [pretend.call(expected)]
        assert blob.upload_from_filename.calls == [pretend.call(filename)]

    def test_stores_two_files(self, tmpdir):
        filename1 = str(tmpdir.join("testfile1.txt"))
        with open(filename1, "wb") as fp:
            fp.write(b"First Test File!")

        filename2 = str(tmpdir.join("testfile2.txt"))
        with open(filename2, "wb") as fp:
            fp.write(b"Second Test File!")

        blob = pretend.stub(
            upload_from_filename=pretend.call_recorder(lambda file_path: None),
            exists=lambda: False,
        )
        bucket = pretend.stub(blob=pretend.call_recorder(lambda path: blob))
        storage = GCSFileStorage(bucket)
        storage.store("foo/first.txt", filename1)
        storage.store("foo/second.txt", filename2)

        assert bucket.blob.calls == [
            pretend.call("foo/first.txt"),
            pretend.call("foo/second.txt"),
        ]
        assert blob.upload_from_filename.calls == [
            pretend.call(filename1),
            pretend.call(filename2),
        ]

    def test_stores_metadata(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        blob = pretend.stub(
            upload_from_filename=pretend.call_recorder(lambda file_path: None),
            patch=pretend.call_recorder(lambda: None),
            exists=lambda: False,
        )
        bucket = pretend.stub(blob=pretend.call_recorder(lambda path: blob))
        storage = GCSFileStorage(bucket)
        meta = {"foo": "bar"}
        storage.store("foo/bar.txt", filename, meta=meta)

        assert blob.metadata == meta

    def test_skips_upload_if_file_exists(self, tmpdir, monkeypatch):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        blob = pretend.stub(
            upload_from_filename=pretend.call_recorder(lambda file_path: None),
            exists=lambda: True,
        )
        bucket = pretend.stub(blob=pretend.call_recorder(lambda path: blob))
        storage = GCSFileStorage(bucket)
        capture_message = pretend.call_recorder(lambda message: None)
        monkeypatch.setattr(
            warehouse.packaging.services.sentry_sdk, "capture_message", capture_message
        )

        storage.store("foo/bar.txt", filename)

        assert bucket.blob.calls == [pretend.call("foo/bar.txt")]
        assert blob.upload_from_filename.calls == []
        assert capture_message.calls == [
            pretend.call(f"Skipped uploading duplicate file: {filename}")
        ]


class TestS3DocsStorage:
    def test_verify_service(self):
        assert verifyClass(IDocsStorage, S3DocsStorage)

    def test_create_service(self):
        session = boto3.session.Session(
            aws_access_key_id="foo", aws_secret_access_key="bar"
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda name: session),
            registry=pretend.stub(settings={"docs.bucket": "froblob"}),
        )
        storage = S3DocsStorage.create_service(None, request)

        assert request.find_service.calls == [pretend.call(name="aws.session")]
        assert storage.bucket_name == "froblob"

    @pytest.mark.parametrize("file_count", [66, 100])
    def test_delete_by_prefix(self, file_count):
        files = {"Contents": [{"Key": f"foo/{i}.html"} for i in range(file_count)]}
        s3_client = pretend.stub(
            list_objects_v2=pretend.call_recorder(
                lambda Bucket=None, Prefix=None: files  # noqa: N803
            ),
            delete_objects=pretend.call_recorder(
                lambda Bucket=None, Delete=None: None  # noqa: N803
            ),
        )
        storage = S3DocsStorage(s3_client, "bucket-name")

        storage.remove_by_prefix("foo")

        assert s3_client.list_objects_v2.calls == [
            pretend.call(Bucket="bucket-name", Prefix="foo")
        ]

        assert s3_client.delete_objects.calls == [
            pretend.call(
                Bucket="bucket-name",
                Delete={
                    "Objects": [{"Key": f"foo/{i}.html"} for i in range(file_count)]
                },
            )
        ]

    def test_delete_by_prefix_more_files(self):
        files = {"Contents": [{"Key": f"foo/{i}.html"} for i in range(150)]}
        s3_client = pretend.stub(
            list_objects_v2=pretend.call_recorder(
                lambda Bucket=None, Prefix=None: files  # noqa: N803
            ),
            delete_objects=pretend.call_recorder(
                lambda Bucket=None, Delete=None: None  # noqa: N803
            ),
        )
        storage = S3DocsStorage(s3_client, "bucket-name")

        storage.remove_by_prefix("foo")

        assert s3_client.list_objects_v2.calls == [
            pretend.call(Bucket="bucket-name", Prefix="foo")
        ]

        assert s3_client.delete_objects.calls == [
            pretend.call(
                Bucket="bucket-name",
                Delete={"Objects": [{"Key": f"foo/{i}.html"} for i in range(100)]},
            ),
            pretend.call(
                Bucket="bucket-name",
                Delete={"Objects": [{"Key": f"foo/{i}.html"} for i in range(100, 150)]},
            ),
        ]

    def test_delete_by_prefix_with_storage_prefix(self):
        files = {"Contents": [{"Key": f"docs/foo/{i}.html"} for i in range(150)]}
        s3_client = pretend.stub(
            list_objects_v2=pretend.call_recorder(
                lambda Bucket=None, Prefix=None: files  # noqa: N803
            ),
            delete_objects=pretend.call_recorder(
                lambda Bucket=None, Delete=None: None  # noqa: N803
            ),
        )
        storage = S3DocsStorage(s3_client, "bucket-name", prefix="docs")

        storage.remove_by_prefix("foo")

        assert s3_client.list_objects_v2.calls == [
            pretend.call(Bucket="bucket-name", Prefix="docs/foo")
        ]

        assert s3_client.delete_objects.calls == [
            pretend.call(
                Bucket="bucket-name",
                Delete={"Objects": [{"Key": f"docs/foo/{i}.html"} for i in range(100)]},
            ),
            pretend.call(
                Bucket="bucket-name",
                Delete={
                    "Objects": [{"Key": f"docs/foo/{i}.html"} for i in range(100, 150)]
                },
            ),
        ]


class TestGCSSimpleStorage:
    def test_verify_service(self):
        assert verifyClass(ISimpleStorage, GCSSimpleStorage)

    def test_basic_init(self):
        bucket = pretend.stub()
        storage = GCSSimpleStorage(bucket)
        assert storage.bucket is bucket

    def test_create_service(self):
        service = pretend.stub(
            get_bucket=pretend.call_recorder(lambda bucket_name: pretend.stub())
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda name: service),
            registry=pretend.stub(settings={"simple.bucket": "froblob"}),
        )
        GCSSimpleStorage.create_service(None, request)

        assert request.find_service.calls == [pretend.call(name="gcloud.gcs")]
        assert service.get_bucket.calls == [pretend.call("froblob")]

    def test_gets_file_raises(self):
        storage = GCSSimpleStorage(pretend.stub())

        with pytest.raises(NotImplementedError):
            storage.get("file.txt")

    def test_stores_file(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        blob = pretend.stub(
            upload_from_filename=pretend.call_recorder(lambda file_path: None),
            exists=lambda: False,
        )
        bucket = pretend.stub(blob=pretend.call_recorder(lambda path: blob))
        storage = GCSSimpleStorage(bucket)
        storage.store("foo/bar.txt", filename)

        assert bucket.blob.calls == [pretend.call("foo/bar.txt")]
        assert blob.upload_from_filename.calls == [pretend.call(filename)]

    def test_stores_two_files(self, tmpdir):
        filename1 = str(tmpdir.join("testfile1.txt"))
        with open(filename1, "wb") as fp:
            fp.write(b"First Test File!")

        filename2 = str(tmpdir.join("testfile2.txt"))
        with open(filename2, "wb") as fp:
            fp.write(b"Second Test File!")

        blob = pretend.stub(
            upload_from_filename=pretend.call_recorder(lambda file_path: None),
            exists=lambda: False,
        )
        bucket = pretend.stub(blob=pretend.call_recorder(lambda path: blob))
        storage = GCSSimpleStorage(bucket)
        storage.store("foo/first.txt", filename1)
        storage.store("foo/second.txt", filename2)

        assert bucket.blob.calls == [
            pretend.call("foo/first.txt"),
            pretend.call("foo/second.txt"),
        ]
        assert blob.upload_from_filename.calls == [
            pretend.call(filename1),
            pretend.call(filename2),
        ]

    def test_stores_metadata(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        blob = pretend.stub(
            upload_from_filename=pretend.call_recorder(lambda file_path: None),
            patch=pretend.call_recorder(lambda: None),
            exists=lambda: False,
        )
        bucket = pretend.stub(blob=pretend.call_recorder(lambda path: blob))
        storage = GCSSimpleStorage(bucket)
        meta = {"foo": "bar"}
        storage.store("foo/bar.txt", filename, meta=meta)

        assert blob.metadata == meta


class TestGenericLocalBlobStorage:
    def test_notimplementederror(self):
        with pytest.raises(NotImplementedError):
            GenericLocalBlobStorage.create_service(pretend.stub(), pretend.stub())


class TestProjectService:
    def test_verify_service(self):
        assert verifyClass(IProjectService, ProjectService)

    @pytest.mark.parametrize("name", ["", ".,;", "_z", "İnspect"])
    def test_check_project_name_invalid(self, name):
        service = ProjectService(session=pretend.stub())

        with pytest.raises(ProjectNameUnavailableInvalidError):
            service.check_project_name(name)

    @pytest.mark.parametrize("name", ["uu", "cgi", "nis", "mailcap"])
    def test_check_project_name_stdlib(self, name):
        service = ProjectService(session=pretend.stub())

        with pytest.raises(ProjectNameUnavailableStdlibError):
            service.check_project_name(name)

    def test_check_project_test_new_disallowed(self, db_request):
        admin_flag = (
            db_request.db.query(AdminFlag)
            .filter(
                AdminFlag.id == AdminFlagValue.DISALLOW_NEW_PROJECT_REGISTRATION.value
            )
            .first()
        )
        admin_flag.enabled = True

        db_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")

        service = ProjectService(session=db_request.db)

        with pytest.raises(HTTPForbidden) as exc:
            service.create_project("foo", pretend.stub(), db_request, ratelimited=False)

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

        with pytest.raises(TooManyProjectsCreated):
            enforce(project_service, db_request, creator)

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

        project_service._hit_ratelimits(db_request, creator)

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

        project_service._check_ratelimits(db_request, creator)

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

    def test_organization_ratelimiter_uses_default_without_override(
        self, project_service, ratelimit_service
    ):
        """With no per-org override, the shared organization-tier default
        limiter (registered like project.create.user/.ip) governs."""
        organization = OrganizationFactory.create(project_create_ratelimit_string=None)
        project_service.ratelimiters["project.create.organization"] = ratelimit_service

        limiter = project_service._organization_ratelimiter(organization)

        assert limiter is ratelimit_service

    def test_organization_ratelimiter_delegates_to_override(self, project_service):
        """A per-org override string is applied via the default limiter's
        own `.override()`, not by hand-building a new RateLimiter."""
        organization = OrganizationFactory.create(
            project_create_ratelimit_string="200 per hour"
        )
        overridden = pretend.stub()
        default_limiter = pretend.stub(
            override=pretend.call_recorder(lambda limit_string: overridden)
        )
        project_service.ratelimiters["project.create.organization"] = default_limiter

        limiter = project_service._organization_ratelimiter(organization)

        assert default_limiter.override.calls == [pretend.call("200 per hour")]
        assert limiter is overridden

    def test_identity_ratelimiter_defaults_to_user(
        self, project_service, ratelimit_service
    ):
        creator = UserFactory.create()
        project_service.ratelimiters["project.create.user"] = ratelimit_service

        limiter, identifier, partition_key = project_service._identity_ratelimiter(
            creator, None
        )

        assert limiter is ratelimit_service
        assert identifier == creator.id
        assert partition_key == "user"

    def test_identity_ratelimiter_uses_user_override_when_set(self, project_service):
        """A per-user override string is applied via the default per-user
        limiter's own `.override()`, the same way organization overrides
        are — see `_organization_ratelimiter`."""
        creator = UserFactory.create(project_create_ratelimit_string="5 per hour")
        overridden = pretend.stub()
        default_limiter = pretend.stub(
            override=pretend.call_recorder(lambda limit_string: overridden)
        )
        project_service.ratelimiters["project.create.user"] = default_limiter

        limiter, identifier, partition_key = project_service._identity_ratelimiter(
            creator, None
        )

        assert default_limiter.override.calls == [pretend.call("5 per hour")]
        assert limiter is overridden
        assert identifier == creator.id
        assert partition_key == "user"

    def test_identity_ratelimiter_uses_organization_when_scoped(
        self, project_service, ratelimit_service
    ):
        creator = UserFactory.create()
        organization = OrganizationFactory.create()
        project_service.ratelimiters["project.create.organization"] = ratelimit_service

        limiter, identifier, partition_key = project_service._identity_ratelimiter(
            creator, organization.id
        )

        assert limiter is ratelimit_service
        assert identifier == organization.id
        assert partition_key == "organization"

    @pytest.mark.parametrize(
        ("enforce", "limiter_method"),
        [
            (ProjectService._check_ratelimits, "test"),
            (ProjectService._hit_ratelimits, "hit"),
        ],
        ids=["check", "hit"],
    )
    def test_ratelimit_exceeded_for_organization_raises_with_correct_reset_hint(
        self,
        project_service,
        db_request,
        ratelimit_service,
        mocker,
        enforce,
        limiter_method,
    ):
        """Creating a project for an organization is governed by that
        organization's rate limit, keyed on the organization's id, instead of
        the creator's individual per-user limit."""
        creator = UserFactory.create()
        organization = OrganizationFactory.create()
        project_service.ratelimiters["project.create.organization"] = ratelimit_service
        mocker.patch.object(ratelimit_service, limiter_method, return_value=False)

        with pytest.raises(TooManyProjectsCreated):
            enforce(project_service, db_request, creator, organization.id)

        ratelimit_service.resets_in.assert_called_once_with(organization.id)

    def test_check_ratelimits_for_organization_does_not_consult_user_limiter(
        self, project_service, db_request, ratelimit_service
    ):
        creator = UserFactory.create()
        organization = OrganizationFactory.create()
        project_service.ratelimiters["project.create.user"] = ratelimit_service
        project_service.ratelimiters["project.create.organization"] = DummyRateLimiter()

        project_service._check_ratelimits(db_request, creator, organization.id)

        ratelimit_service.test.assert_not_called()

    def test_check_ratelimits_for_organization_still_checks_ip_limiter(
        self, project_service, db_request, ratelimit_service, mocker
    ):
        """The IP limiter is an orthogonal anti-abuse measure and still
        applies even when the organization-tier limiter takes over from the
        per-user limiter."""
        creator = UserFactory.create()
        organization = OrganizationFactory.create()
        project_service.ratelimiters["project.create.ip"] = ratelimit_service
        project_service.ratelimiters["project.create.organization"] = DummyRateLimiter()
        mocker.patch.object(ratelimit_service, "test", return_value=False)

        with pytest.raises(TooManyProjectsCreated):
            project_service._check_ratelimits(db_request, creator, organization.id)

        ratelimit_service.resets_in.assert_called_once_with(db_request.remote_addr)

    def test_check_ratelimits_uses_organization_override_when_set(
        self, project_service, db_request
    ):
        creator = UserFactory.create()
        organization = OrganizationFactory.create(
            project_create_ratelimit_string="5 per hour"
        )
        overridden = pretend.stub(
            test=pretend.call_recorder(lambda *a: True),
            resets_in=pretend.call_recorder(lambda *a: None),
            get_window_stats=pretend.call_recorder(lambda *a: []),
        )
        project_service.ratelimiters["project.create.organization"] = pretend.stub(
            override=pretend.call_recorder(lambda limit_string: overridden)
        )

        project_service._check_ratelimits(db_request, creator, organization.id)

        assert overridden.test.calls == [pretend.call(organization.id)]

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

    def test_create_project_skips_owner_role_and_org_link_when_neither_applies(
        self, project_service, db_request
    ):
        """`creator_is_owner=False` with no `organization_id` skips both the
        owner-Role assignment and the OrganizationProject link — a project
        created this way ends up with neither."""
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
        """Linking a new project to an organization inline must purge that
        org's cached project listing too — not just links made through
        IOrganizationService.add_organization_project (e.g. the OIDC
        trusted-publisher auto-create path never calls that service method,
        it only goes through create_project)."""
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

    def test_check_project_name_typosquatting_prohibited(self, db_session):
        # TODO: Update this test once we have a dynamic TopN approach
        service = ProjectService(session=db_session)
        ProhibitedProjectFactory.create(name="numpy")

        with pytest.raises(ProjectNameUnavailableTypoSquattingError):
            service.check_project_name("numpi")

    def test_check_project_name_ok(self, db_session):
        service = ProjectService(session=db_session)

        # Should not raise any exception
        service.check_project_name("foo")


def test_project_service_factory(db_request, ratelimit_service):
    service = project_service_factory(pretend.stub(), db_request)

    assert service.db is db_request.db
    # The factory resolves all three rate limiters from the registry by name.
    assert service.ratelimiters["project.create.user"] is ratelimit_service
    assert service.ratelimiters["project.create.ip"] is ratelimit_service
    assert service.ratelimiters["project.create.organization"] is ratelimit_service
