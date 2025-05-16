# SPDX-License-Identifier: Apache-2.0

import os.path

import pretend

from zope.interface.verify import verifyClass

from warehouse.admin.interfaces import ISponsorLogoStorage
from warehouse.admin.services import GCSSponsorLogoStorage, LocalSponsorLogoStorage


class TestSponsorLogoStorage:
    def test_verify_service(self):
        assert verifyClass(ISponsorLogoStorage, LocalSponsorLogoStorage)

    def test_basic_init(self):
        storage = LocalSponsorLogoStorage("/foo/bar/")
        assert storage.base == "/foo/bar/"

    def test_create_service(self):
        request = pretend.stub(
            registry=pretend.stub(settings={"sponsorlogos.path": "/the/one/two/"})
        )
        storage = LocalSponsorLogoStorage.create_service(None, request)
        assert storage.base == "/the/one/two/"

    def test_stores_file(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        storage_dir = str(tmpdir.join("storage"))
        storage = LocalSponsorLogoStorage(storage_dir)
        result = storage.store("foo/bar.txt", filename)

        assert result == "http://files:9001/sponsorlogos/foo/bar.txt"
        with open(os.path.join(storage_dir, "foo/bar.txt"), "rb") as fp:
            assert fp.read() == b"Test File!"


class TestGCSSponsorLogoStorage:
    def test_verify_service(self):
        assert verifyClass(ISponsorLogoStorage, GCSSponsorLogoStorage)

    def test_basic_init(self):
        bucket = pretend.stub()
        storage = GCSSponsorLogoStorage(bucket)
        assert storage.bucket is bucket

    def test_create_service(self):
        service = pretend.stub(
            get_bucket=pretend.call_recorder(lambda bucket_name: pretend.stub())
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda name: service),
            registry=pretend.stub(settings={"sponsorlogos.bucket": "froblob"}),
        )
        GCSSponsorLogoStorage.create_service(None, request)

        assert request.find_service.calls == [pretend.call(name="gcloud.gcs")]
        assert service.get_bucket.calls == [pretend.call("froblob")]

    def test_stores_file(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        blob = pretend.stub(
            upload_from_filename=pretend.call_recorder(lambda file_path: None),
            make_public=pretend.call_recorder(lambda: None),
            public_url="http://files/sponsorlogos/thelogo.png",
            content_type=None,
        )
        bucket = pretend.stub(blob=pretend.call_recorder(lambda path: blob))
        storage = GCSSponsorLogoStorage(bucket)
        result = storage.store("foo/bar.txt", filename)

        assert result == "http://files/sponsorlogos/thelogo.png"
        assert bucket.blob.calls == [pretend.call("foo/bar.txt")]
        assert blob.make_public.calls == [pretend.call()]
        assert blob.upload_from_filename.calls == [pretend.call(filename)]

    def test_stores_file_with_prefix(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        blob = pretend.stub(
            upload_from_filename=pretend.call_recorder(lambda file_path: None),
            make_public=pretend.call_recorder(lambda: None),
            public_url="http://files/sponsorlogos/thelogo.png",
            content_type=pretend.call_recorder(lambda x: None),
        )
        bucket = pretend.stub(blob=pretend.call_recorder(lambda path: blob))
        storage = GCSSponsorLogoStorage(bucket, prefix="sponsorlogos")
        result = storage.store("foo/bar.txt", filename)

        assert result == "http://files/sponsorlogos/thelogo.png"
        assert bucket.blob.calls == [pretend.call("sponsorlogos/foo/bar.txt")]
        assert blob.make_public.calls == [pretend.call()]
        assert blob.upload_from_filename.calls == [pretend.call(filename)]

    def test_stores_metadata(self, tmpdir):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        blob = pretend.stub(
            upload_from_filename=pretend.call_recorder(lambda file_path: None),
            make_public=pretend.call_recorder(lambda: None),
            public_url="http://files/sponsorlogos/thelogo.png",
            patch=pretend.call_recorder(lambda: None),
            content_type=None,
        )
        bucket = pretend.stub(blob=pretend.call_recorder(lambda path: blob))
        storage = GCSSponsorLogoStorage(bucket)
        meta = {"foo": "bar"}
        result = storage.store("foo/bar.txt", filename, "image/png", meta=meta)

        assert result == "http://files/sponsorlogos/thelogo.png"
        assert blob.make_public.calls == [pretend.call()]
        assert blob.content_type == "image/png"
        assert blob.metadata == meta
