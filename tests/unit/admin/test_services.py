# SPDX-License-Identifier: Apache-2.0

import os.path

import google.cloud.storage
import pytest

from zope.interface.verify import verifyClass

from warehouse.admin.interfaces import ISponsorLogoStorage
from warehouse.admin.services import GCSSponsorLogoStorage, LocalSponsorLogoStorage


@pytest.fixture
def gcs_blob(mocker):
    blob = mocker.create_autospec(google.cloud.storage.Blob, instance=True)
    blob.public_url = "http://files/sponsorlogos/thelogo.png"
    return blob


@pytest.fixture
def gcs_bucket(mocker, gcs_blob):
    bucket = mocker.create_autospec(google.cloud.storage.Bucket, instance=True)
    bucket.blob.return_value = gcs_blob
    return bucket


class TestSponsorLogoStorage:
    def test_verify_service(self):
        assert verifyClass(ISponsorLogoStorage, LocalSponsorLogoStorage)

    def test_basic_init(self):
        storage = LocalSponsorLogoStorage("/foo/bar/")
        assert storage.base == "/foo/bar/"

    def test_create_service(self, mocker):
        request = mocker.Mock(spec=["registry"])
        request.registry.settings = {"sponsorlogos.path": "/the/one/two/"}
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

    def test_basic_init(self, gcs_bucket):
        storage = GCSSponsorLogoStorage(gcs_bucket)
        assert storage.bucket is gcs_bucket

    def test_create_service(self, mocker, gcs_bucket):
        client = mocker.create_autospec(google.cloud.storage.Client, instance=True)
        client.get_bucket.return_value = gcs_bucket
        request = mocker.Mock(spec=["find_service", "registry"])
        request.find_service.return_value = client
        request.registry.settings = {"sponsorlogos.bucket": "froblob"}

        storage = GCSSponsorLogoStorage.create_service(None, request)

        request.find_service.assert_called_once_with(name="gcloud.gcs")
        client.get_bucket.assert_called_once_with("froblob")
        assert storage.bucket is gcs_bucket
        assert storage.prefix is None

    def test_stores_file(self, tmpdir, gcs_bucket, gcs_blob):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        storage = GCSSponsorLogoStorage(gcs_bucket)
        result = storage.store("foo/bar.txt", filename)

        assert result == "http://files/sponsorlogos/thelogo.png"
        gcs_bucket.blob.assert_called_once_with("foo/bar.txt")
        gcs_blob.make_public.assert_called_once_with()
        gcs_blob.upload_from_filename.assert_called_once_with(filename)
        assert gcs_blob.content_type is None

    def test_stores_file_with_prefix(self, tmpdir, gcs_bucket, gcs_blob):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        storage = GCSSponsorLogoStorage(gcs_bucket, prefix="sponsorlogos")
        result = storage.store("foo/bar.txt", filename)

        assert result == "http://files/sponsorlogos/thelogo.png"
        gcs_bucket.blob.assert_called_once_with("sponsorlogos/foo/bar.txt")
        gcs_blob.make_public.assert_called_once_with()
        gcs_blob.upload_from_filename.assert_called_once_with(filename)

    def test_stores_metadata(self, tmpdir, gcs_bucket, gcs_blob):
        filename = str(tmpdir.join("testfile.txt"))
        with open(filename, "wb") as fp:
            fp.write(b"Test File!")

        storage = GCSSponsorLogoStorage(gcs_bucket)
        meta = {"foo": "bar"}
        result = storage.store("foo/bar.txt", filename, "image/png", meta=meta)

        assert result == "http://files/sponsorlogos/thelogo.png"
        gcs_blob.make_public.assert_called_once_with()
        assert gcs_blob.content_type == "image/png"
        assert gcs_blob.metadata == meta
