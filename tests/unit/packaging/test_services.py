# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import io
import os.path

import boto3.session
import botocore.exceptions
import pretend
import pytest

from zope.interface.verify import verifyClass

from warehouse.packaging import services
from warehouse.packaging.interfaces import IDocsStorage, IFileStorage
from warehouse.packaging.services import (
    DualFileStorage,
    GCSFileStorage,
    LocalDocsStorage,
    LocalFileStorage,
    S3DocsStorage,
    S3FileStorage,
)


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


class TestS3FileStorage:
    def test_verify_service(self):
        assert verifyClass(IFileStorage, S3FileStorage)

    def test_basic_init(self):
        bucket = pretend.stub()
        storage = S3FileStorage(bucket)
        assert storage.bucket is bucket

    def test_create_service(self):
        session = boto3.session.Session()
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

    def test_stores_file(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        bucket = pretend.stub(
            upload_file=pretend.call_recorder(lambda filename, key, ExtraArgs: None)
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
            upload_file=pretend.call_recorder(lambda filename, key, ExtraArgs: None)
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
            upload_file=pretend.call_recorder(lambda filename, key, ExtraArgs: None)
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

    def test_stores_file(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        blob = pretend.stub(
            upload_from_filename=pretend.call_recorder(lambda file_path: None)
        )
        bucket = pretend.stub(blob=pretend.call_recorder(lambda path: blob))
        storage = GCSFileStorage(bucket)
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
            upload_from_filename=pretend.call_recorder(lambda file_path: None)
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
        )
        bucket = pretend.stub(blob=pretend.call_recorder(lambda path: blob))
        storage = GCSFileStorage(bucket)
        meta = {"foo": "bar"}
        storage.store("foo/bar.txt", filename, meta=meta)

        assert blob.metadata == meta
        assert blob.patch.calls == [pretend.call()]


class TestDualFileStorage:
    def test_verify_service(self):
        assert verifyClass(IFileStorage, DualFileStorage)

    def test_basic_init(self):
        bucket = pretend.stub()
        storage = DualFileStorage(bucket)
        assert storage.bucket is bucket

    def test_create_service(self, monkeypatch):
        def proxy_factory(a):
            return pretend.call(a)

        monkeypatch.setattr(services, "ProxyFactory", proxy_factory)
        request = pretend.stub(
            registry=pretend.stub(settings={"files.bucket": "froblob"}),
            services=pretend.stub(
                register_factory=pretend.call_recorder(lambda factory, name: None)
            ),
        )
        storage = DualFileStorage.create_service(None, request)

        assert request.services.register_factory.calls == [
            pretend.call(
                pretend.call(S3FileStorage.create_service), name="primary-file-backend"
            ),
            pretend.call(
                pretend.call(GCSFileStorage.create_service),
                name="secondary-file-backend",
            ),
        ]
        assert storage.request == request

    def test_gets_file_raises(self):
        storage = DualFileStorage(None)

        with pytest.raises(NotImplementedError):
            storage.get("file.txt")

    def test_stores_file(self, tmpdir, monkeypatch):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        def proxy_factory(a):
            return pretend.call(a)

        monkeypatch.setattr(services, "ProxyFactory", proxy_factory)

        primary_service = pretend.stub(
            store=pretend.call_recorder(lambda *a, **kw: None)
        )
        secondary_service = pretend.stub(
            store=pretend.call_recorder(lambda *a, **kw: None)
        )
        registered_services = {
            "primary-file-backend": primary_service,
            "secondary-file-backend": secondary_service,
        }
        request = pretend.stub(
            find_service=pretend.call_recorder(
                lambda name: registered_services.get(name)
            ),
            registry=pretend.stub(settings={"files.bucket": "froblob"}),
            services=pretend.stub(
                register_factory=pretend.call_recorder(lambda factory, name: None)
            ),
        )
        storage = DualFileStorage.create_service(None, request)
        meta = pretend.stub()
        storage.store("foo/bar.txt", filename, meta=meta)

        assert request.find_service.calls == [
            pretend.call(name="primary-file-backend"),
            pretend.call(name="secondary-file-backend"),
        ]
        assert primary_service.store.calls == [
            pretend.call("foo/bar.txt", filename, meta=meta)
        ]
        assert secondary_service.store.calls == [
            pretend.call("foo/bar.txt", filename, meta=meta)
        ]

    def test_succeeds_if_secondary_fails(self, tmpdir, monkeypatch):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        def proxy_factory(a):
            return pretend.call(a)

        monkeypatch.setattr(services, "ProxyFactory", proxy_factory)

        primary_service = pretend.stub(
            store=pretend.call_recorder(lambda *a, **kw: None)
        )
        secondary_service = pretend.stub(
            store=pretend.call_recorder(pretend.raiser(Exception))
        )
        registered_services = {
            "primary-file-backend": primary_service,
            "secondary-file-backend": secondary_service,
        }
        request = pretend.stub(
            find_service=pretend.call_recorder(
                lambda name: registered_services.get(name)
            ),
            registry=pretend.stub(settings={"files.bucket": "froblob"}),
            services=pretend.stub(
                register_factory=pretend.call_recorder(lambda factory, name: None)
            ),
        )
        storage = DualFileStorage.create_service(None, request)
        meta = pretend.stub()
        storage.store("foo/bar.txt", filename, meta=meta)

        assert request.find_service.calls == [
            pretend.call(name="primary-file-backend"),
            pretend.call(name="secondary-file-backend"),
        ]
        assert primary_service.store.calls == [
            pretend.call("foo/bar.txt", filename, meta=meta)
        ]
        assert secondary_service.store.calls == [
            pretend.call("foo/bar.txt", filename, meta=meta)
        ]


class TestS3DocsStorage:
    def test_verify_service(self):
        assert verifyClass(IDocsStorage, S3DocsStorage)

    def test_create_service(self):
        session = boto3.session.Session()
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
                lambda Bucket=None, Prefix=None: files
            ),
            delete_objects=pretend.call_recorder(lambda Bucket=None, Delete=None: None),
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
                lambda Bucket=None, Prefix=None: files
            ),
            delete_objects=pretend.call_recorder(lambda Bucket=None, Delete=None: None),
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
                lambda Bucket=None, Prefix=None: files
            ),
            delete_objects=pretend.call_recorder(lambda Bucket=None, Delete=None: None),
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
