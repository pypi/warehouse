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
import freezegun
import pretend
import pytest
import redis

from zope.interface.verify import verifyClass

from warehouse.packaging.interfaces import IDownloadStatService, IFileStorage
from warehouse.packaging.services import (
    RedisDownloadStatService, LocalFileStorage, S3FileStorage,
)


@freezegun.freeze_time("2012-01-14")
class TestRedisDownloadStatService:

    def test_verify_service(self):
        assert verifyClass(IDownloadStatService, RedisDownloadStatService)

    def test_creates_redis(self, monkeypatch):
        redis_obj = pretend.stub()
        redis_cls = pretend.stub(
            from_url=pretend.call_recorder(lambda u: redis_obj),
        )
        monkeypatch.setattr(redis, "StrictRedis", redis_cls)

        url = pretend.stub()
        svc = RedisDownloadStatService(url)

        assert svc.redis is redis_obj
        assert redis_cls.from_url.calls == [pretend.call(url)]

    @pytest.mark.parametrize(
        ("keys", "result"),
        [
            ([], 0),
            ([5, 7, 8], 20),
        ]
    )
    def test_get_daily_stats(self, keys, result):
        svc = RedisDownloadStatService("")
        svc.redis = pretend.stub(mget=pretend.call_recorder(lambda *a: keys))

        call_keys = (
            ["downloads:hour:12-01-14-00:foo"] +
            [
                "downloads:hour:12-01-13-{:02d}:foo".format(i)
                for i in reversed(range(24))
            ] +
            ["downloads:hour:12-01-12-23:foo"]
        )

        assert svc.get_daily_stats("foo") == result
        assert svc.redis.mget.calls == [pretend.call(*call_keys)]

    @pytest.mark.parametrize(
        ("keys", "result"),
        [
            ([], 0),
            ([5, 7, 8], 20),
        ]
    )
    def test_get_weekly_stats(self, keys, result):
        svc = RedisDownloadStatService("")
        svc.redis = pretend.stub(mget=pretend.call_recorder(lambda *a: keys))

        call_keys = [
            "downloads:daily:12-01-{:02d}:foo".format(i + 7)
            for i in reversed(range(8))
        ]

        assert svc.get_weekly_stats("foo") == result
        assert svc.redis.mget.calls == [pretend.call(*call_keys)]

    @pytest.mark.parametrize(
        ("keys", "result"),
        [
            ([], 0),
            ([5, 7, 8], 20),
        ]
    )
    def test_get_monthly_stats(self, keys, result):
        svc = RedisDownloadStatService("")
        svc.redis = pretend.stub(mget=pretend.call_recorder(lambda *a: keys))

        call_keys = [
            "downloads:daily:12-01-{:02d}:foo".format(i)
            for i in reversed(range(1, 15))
        ] + [
            "downloads:daily:11-12-{:02d}:foo".format(i + 15)
            for i in reversed(range(17))
        ]

        assert svc.get_monthly_stats("foo") == result
        assert svc.redis.mget.calls == [pretend.call(*call_keys)]


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
        storage = LocalFileStorage.create_service(None, request)
        assert storage.base == "/the/one/two/"

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

    def test_raises_when_key_non_existant(self):
        def raiser():
            raise botocore.exceptions.ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "No Key!"}},
                "some operation",
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
        bucket = pretend.stub(Object=lambda path: s3key)
        storage = S3FileStorage(bucket)

        with pytest.raises(botocore.exceptions.ClientError):
            storage.get("file.txt")

    def test_stores_file(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        bucket = pretend.stub(
            upload_file=pretend.call_recorder(
                lambda filename, key, ExtraArgs: None,
            ),
        )
        storage = S3FileStorage(bucket)
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

        bucket = pretend.stub(
            upload_file=pretend.call_recorder(
                lambda filename, key, ExtraArgs: None,
            ),
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
                lambda filename, key, ExtraArgs: None,
            ),
        )
        storage = S3FileStorage(bucket)
        storage.store("foo/bar.txt", filename, meta={"foo": "bar"})

        assert bucket.upload_file.calls == [
            pretend.call(
                filename,
                "foo/bar.txt",
                ExtraArgs={"Metadata": {"foo": "bar"}},
            ),
        ]
