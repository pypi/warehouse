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

import os.path
import warnings

import botocore.exceptions

from zope.interface import implementer

from warehouse.packaging.interfaces import IFileStorage


@implementer(IFileStorage)
class LocalFileStorage:

    def __init__(self, base):
        # This class should not be used in production, it's trivial for it to
        # be used to read arbitrary files from the disk. It is intended ONLY
        # for local development with trusted users. To make this clear, we'll
        # raise a warning.
        warnings.warn(
            "LocalFileStorage is intended only for use in development, you "
            "should not use it in production due to the lack of safe guards "
            "for safely locating files on disk.",
            RuntimeWarning,
        )

        self.base = base

    @classmethod
    def create_service(cls, context, request):
        return cls(request.registry.settings["files.path"])

    def get(self, path):
        return open(os.path.join(self.base, path), "rb")

    def store(self, path, file_path, *, meta=None):
        destination = os.path.join(self.base, path)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with open(destination, "wb") as dest_fp:
            with open(file_path, "rb") as src_fp:
                dest_fp.write(src_fp.read())


@implementer(IFileStorage)
class S3FileStorage:

    def __init__(self, bucket, *, prefix=None):
        self.bucket = bucket
        self.prefix = prefix

    @classmethod
    def create_service(cls, context, request):
        session = request.find_service(name="aws.session")
        s3 = session.resource("s3")
        bucket = s3.Bucket(request.registry.settings["files.bucket"])
        prefix = request.registry.settings.get("files.prefix")
        return cls(bucket, prefix=prefix)

    def _get_path(self, path):
        # Legacy paths will have a first directory of something like 2.7, we
        # want to just continue to support them for now.
        if len(path.split("/")[0]) > 2:
            return path

        # If we have a prefix, then prepend it to our path. This will let us
        # store items inside of a sub directory without exposing that to end
        # users.
        if self.prefix:
            path = self.prefix + path

        return path

    def get(self, path):
        try:
            return self.bucket.Object(self._get_path(path)).get()["Body"]
        except botocore.exceptions.ClientError as exc:
            if exc.response["Error"]["Code"] != "NoSuchKey":
                raise
            raise FileNotFoundError("No such key: {!r}".format(path)) from None

    def store(self, path, file_path, *, meta=None):
        extra_args = {}
        if meta is not None:
            extra_args["Metadata"] = meta

        path = self._get_path(path)

        self.bucket.upload_file(file_path, path, ExtraArgs=extra_args)
