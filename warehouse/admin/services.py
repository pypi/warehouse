# SPDX-License-Identifier: Apache-2.0

import os.path
import warnings

import google.api_core.exceptions
import google.api_core.retry

from zope.interface import implementer

from warehouse.admin.interfaces import ISponsorLogoStorage
from warehouse.utils.exceptions import DevelopmentModeWarning


class InsecureStorageWarning(DevelopmentModeWarning):
    pass


@implementer(ISponsorLogoStorage)
class LocalSponsorLogoStorage:
    def __init__(self, base):
        # This class should not be used in production, it's trivial for it to
        # be used to read arbitrary files from the disk. It is intended ONLY
        # for local development with trusted users. To make this clear, we'll
        # raise a warning.
        warnings.warn(
            "LocalSponsorLogoStorage is intended only for use in development, you "
            "should not use it in production due to the lack of safe guards "
            "for safely locating files on disk.",
            InsecureStorageWarning,
        )

        self.base = base

    @classmethod
    def create_service(cls, context, request):
        return cls(request.registry.settings["sponsorlogos.path"])

    def store(self, path, file_path, content_type=None, *, meta=None):
        destination = os.path.join(self.base, path)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with open(destination, "wb") as dest_fp:
            with open(file_path, "rb") as src_fp:
                dest_fp.write(src_fp.read())
                dest_fp.flush()
        return f"http://files:9001/sponsorlogos/{path}"


class GenericSponsorLogoStorage:
    def __init__(self, bucket, *, prefix=None):
        self.bucket = bucket
        self.prefix = prefix


@implementer(ISponsorLogoStorage)
class GCSSponsorLogoStorage(GenericSponsorLogoStorage):
    @classmethod
    @google.api_core.retry.Retry(
        predicate=google.api_core.retry.if_exception_type(
            google.api_core.exceptions.ServiceUnavailable
        )
    )
    def create_service(cls, context, request):
        storage_client = request.find_service(name="gcloud.gcs")
        bucket_name = request.registry.settings["sponsorlogos.bucket"]
        bucket = storage_client.get_bucket(bucket_name)
        prefix = request.registry.settings.get("sponsorlogos.prefix")

        return cls(bucket, prefix=prefix)

    @google.api_core.retry.Retry(
        predicate=google.api_core.retry.if_exception_type(
            google.api_core.exceptions.ServiceUnavailable
        )
    )
    def store(self, path, file_path, content_type=None, *, meta=None):
        if self.prefix is not None:
            path = os.path.join(self.prefix, path)
        blob = self.bucket.blob(path)
        blob.content_type = content_type
        if meta is not None:
            blob.metadata = meta
        blob.upload_from_filename(file_path)
        blob.make_public()
        return blob.public_url
