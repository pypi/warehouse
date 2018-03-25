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

from warehouse.packaging.interfaces import IFileStorage
from warehouse.packaging.services import LocalFileStorage, S3FileStorage


class TestLocalFileStorage:

    def test_verify_service(self):
        assert verifyClass(IFileStorage, LocalFileStorage)

    def test_basic_init(self):
        storage = LocalFileStorage("/foo/bar/")
        assert storage.base == "/foo/bar/"

    def test_create_service(self):
        request = pretend.stub(
            registry=pretend.stub(
                settings={"files.path": "/the/one/two/"},
            ),
        )
        storage = LocalFileStorage.create_service(None, request, name='files')
        assert storage.base == "/the/one/two/"

    def test_create_service_no_name(self):
        request = pretend.stub(
            registry=pretend.stub(
                settings={"files.path": "/the/one/two/"},
            ),
        )
        with pytest.raises(ValueError):
            LocalFileStorage.create_service(None, request)

    def test_gets_file(self, tmpdir):
        with open(str(tmpdir.join("file.txt")), "wb") as fp:
            fp.write(b"my test file contents")

        storage = LocalFileStorage(str(tmpdir))
        file_object = storage.get("file.txt")
        assert file_object.read() == b"my test file contents"

    def test_raises_when_file_non_existant(self, tmpdir):
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

    def test_delete_by_prefix(self, tmpdir):
        filename0 = str(tmpdir.join("testfile0.txt"))
        with open(filename0, "wb") as fp:
            fp.write(b"Zeroth Test File!")

        filename1 = str(tmpdir.join("testfile1.txt"))
        with open(filename1, "wb") as fp:
            fp.write(b"First Test File!")

        filename2 = str(tmpdir.join("testfile2.txt"))
        with open(filename2, "wb") as fp:
            fp.write(b"Second Test File!")

        storage_dir = str(tmpdir.join("storage"))
        storage = LocalFileStorage(storage_dir)
        storage.store("foo/zeroth.txt", filename0)
        storage.store("foo/first.txt", filename1)
        storage.store("bar/second.txt", filename2)

        with open(os.path.join(storage_dir, "foo/zeroth.txt"), "rb") as fp:
            assert fp.read() == b"Zeroth Test File!"

        with open(os.path.join(storage_dir, "foo/first.txt"), "rb") as fp:
            assert fp.read() == b"First Test File!"

        with open(os.path.join(storage_dir, "bar/second.txt"), "rb") as fp:
            assert fp.read() == b"Second Test File!"

        storage.remove_by_prefix('foo')

        with pytest.raises(FileNotFoundError):
            storage.get("foo/zeroth.txt")

        with pytest.raises(FileNotFoundError):
            storage.get("foo/first.txt")

        with open(os.path.join(storage_dir, "bar/second.txt"), "rb") as fp:
            assert fp.read() == b"Second Test File!"

    def test_delete_already_gone(self, tmpdir):
        storage_dir = str(tmpdir.join("storage"))
        storage = LocalFileStorage(storage_dir)

        response = storage.remove_by_prefix('foo')
        assert response is None


class TestS3FileStorage:

    def test_verify_service(self):
        assert verifyClass(IFileStorage, S3FileStorage)

    def test_basic_init(self):
        s3_client = pretend.stub()
        bucket = pretend.stub()
        storage = S3FileStorage(s3_client, bucket)
        assert storage.bucket is bucket
        assert storage.s3_client is s3_client

    def test_create_service(self):
        session = boto3.session.Session()
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda name: session),
            registry=pretend.stub(settings={"files.bucket": "froblob"}),
        )
        storage = S3FileStorage.create_service(None, request, name='files')

        assert request.find_service.calls == [pretend.call(name="aws.session")]
        assert storage.bucket.name == "froblob"

    def test_create_service_without_name(self):
        session = boto3.session.Session()
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda name: session),
            registry=pretend.stub(settings={"files.bucket": "froblob"}),
        )
        with pytest.raises(ValueError):
            S3FileStorage.create_service(None, request)

    def test_gets_file(self):
        s3key = pretend.stub(get=lambda: {"Body": io.BytesIO(b"my contents")})
        bucket = pretend.stub(Object=pretend.call_recorder(lambda path: s3key))
        s3_client = pretend.stub()
        storage = S3FileStorage(s3_client, bucket)

        file_object = storage.get("file.txt")

        assert file_object.read() == b"my contents"
        assert bucket.Object.calls == [pretend.call("file.txt")]

    def test_raises_when_key_non_existant(self):
        def raiser():
            raise botocore.exceptions.ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "No Key!"}},
                "some operation",
            )

        s3key = pretend.stub(get=raiser)
        bucket = pretend.stub(Object=pretend.call_recorder(lambda path: s3key))
        s3_client = pretend.stub()
        storage = S3FileStorage(s3_client, bucket)

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
        s3_client = pretend.stub()
        storage = S3FileStorage(s3_client, bucket)

        with pytest.raises(botocore.exceptions.ClientError):
            storage.get("file.txt")

    def test_stores_file(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        s3_client = pretend.stub()
        bucket = pretend.stub(
            upload_file=pretend.call_recorder(
                lambda filename, key, ExtraArgs: None,
            ),
        )
        storage = S3FileStorage(s3_client, bucket)
        storage.store("foo/bar.txt", filename)

        assert bucket.upload_file.calls == [
            pretend.call(filename, "foo/bar.txt", ExtraArgs={}),
        ]

    def test_stores_two_files(self, tmpdir):
        filename1 = str(tmpdir.join("testfile1.txt"))
        with open(filename1, "wb") as fp:
            fp.write(b"First Test File!")

        filename2 = str(tmpdir.join("testfile2.txt"))
        with open(filename2, "wb") as fp:
            fp.write(b"Second Test File!")

        s3_client = pretend.stub()
        bucket = pretend.stub(
            upload_file=pretend.call_recorder(
                lambda filename, key, ExtraArgs: None,
            ),
        )
        storage = S3FileStorage(s3_client, bucket)
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

        s3_client = pretend.stub()
        bucket = pretend.stub(
            upload_file=pretend.call_recorder(
                lambda filename, key, ExtraArgs: None,
            ),
        )
        storage = S3FileStorage(s3_client, bucket)
        storage.store("foo/bar.txt", filename, meta={"foo": "bar"})

        assert bucket.upload_file.calls == [
            pretend.call(
                filename,
                "foo/bar.txt",
                ExtraArgs={"Metadata": {"foo": "bar"}},
            ),
        ]

    def test_hashed_path_with_prefix(self):
        s3key = pretend.stub(get=lambda: {"Body": io.BytesIO(b"my contents")})
        s3_client = pretend.stub()
        bucket = pretend.stub(Object=pretend.call_recorder(lambda path: s3key))
        storage = S3FileStorage(s3_client, bucket, prefix="packages/")

        file_object = storage.get("ab/file.txt")

        assert file_object.read() == b"my contents"
        assert bucket.Object.calls == [pretend.call("packages/ab/file.txt")]

    def test_hashed_path_without_prefix(self):
        s3key = pretend.stub(get=lambda: {"Body": io.BytesIO(b"my contents")})
        s3_client = pretend.stub()
        bucket = pretend.stub(Object=pretend.call_recorder(lambda path: s3key))
        storage = S3FileStorage(s3_client, bucket)

        file_object = storage.get("ab/file.txt")

        assert file_object.read() == b"my contents"
        assert bucket.Object.calls == [pretend.call("ab/file.txt")]

    @pytest.mark.parametrize('file_count', [66, 100])
    def test_delete_by_prefix(self, file_count):
        files = {
            'Contents': [
                {'Key': f'foo/{i}.html'} for i in range(file_count)
            ],
        }
        bucket = pretend.stub(
            name='bucket-name',
        )
        s3_client = pretend.stub(
            list_objects_v2=pretend.call_recorder(
                lambda Bucket=None, Prefix=None: files),
            delete_objects=pretend.call_recorder(
                lambda Bucket=None, Delete=None: None),
        )
        storage = S3FileStorage(s3_client, bucket)

        storage.remove_by_prefix('foo')

        assert s3_client.list_objects_v2.calls == [
            pretend.call(Bucket='bucket-name', Prefix='foo'),
        ]

        assert s3_client.delete_objects.calls == [
            pretend.call(
                Bucket='bucket-name',
                Delete={
                    'Objects': [
                        {'Key': f'foo/{i}.html'} for i in range(file_count)
                    ]
                },
            ),
        ]

    def test_delete_by_prefix_more_files(self):
        files = {
            'Contents': [{'Key': f'foo/{i}.html'} for i in range(150)]
        }
        bucket = pretend.stub(
            name='bucket-name',
        )
        s3_client = pretend.stub(
            list_objects_v2=pretend.call_recorder(
                lambda Bucket=None, Prefix=None: files),
            delete_objects=pretend.call_recorder(
                lambda Bucket=None, Delete=None: None),
        )
        storage = S3FileStorage(s3_client, bucket)

        storage.remove_by_prefix('foo')

        assert s3_client.list_objects_v2.calls == [
            pretend.call(Bucket='bucket-name', Prefix='foo'),
        ]

        assert s3_client.delete_objects.calls == [
            pretend.call(
                Bucket='bucket-name',
                Delete={
                    'Objects': [
                        {'Key': f'foo/{i}.html'} for i in range(100)
                    ]
                },
            ),
            pretend.call(
                Bucket='bucket-name',
                Delete={
                    'Objects': [
                        {'Key': f'foo/{i}.html'} for i in range(100, 150)
                    ]
                },
            )
        ]

    def test_delete_by_prefix_with_storage_prefix(self):
        files = {
            'Contents': [{'Key': f'docs/foo/{i}.html'} for i in range(150)]
        }
        bucket = pretend.stub(
            name='bucket-name',
        )
        s3_client = pretend.stub(
            list_objects_v2=pretend.call_recorder(
                lambda Bucket=None, Prefix=None: files),
            delete_objects=pretend.call_recorder(
                lambda Bucket=None, Delete=None: None),
        )
        storage = S3FileStorage(s3_client, bucket, prefix='docs')

        storage.remove_by_prefix('foo')

        assert s3_client.list_objects_v2.calls == [
            pretend.call(Bucket='bucket-name', Prefix='docs/foo'),
        ]

        assert s3_client.delete_objects.calls == [
            pretend.call(
                Bucket='bucket-name',
                Delete={
                    'Objects': [
                        {'Key': f'docs/foo/{i}.html'} for i in range(100)
                    ]
                },
            ),
            pretend.call(
                Bucket='bucket-name',
                Delete={
                    'Objects': [
                        {'Key': f'docs/foo/{i}.html'} for i in range(100, 150)
                    ]
                },
            )
        ]
