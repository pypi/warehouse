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

import collections
import datetime
import os.path
import warnings

import botocore.exceptions
import redis

from zope.interface import implementer

from warehouse.packaging.interfaces import IDownloadStatService, IFileStorage


_PRECISION = collections.namedtuple(
    "_PRECISION",
    ["type", "delta", "format", "num"],
)

_PRECISIONS = {
    "daily": _PRECISION(
        type="hour", delta="hours", format="%y-%m-%d-%H", num=26,
    ),
    "weekly": _PRECISION(type="daily", delta="days", format="%y-%m-%d", num=8),
    "monthly": _PRECISION(
        type="daily", delta="days", format="%y-%m-%d", num=31,
    ),
}


@implementer(IDownloadStatService)
class RedisDownloadStatService:

    def __init__(self, url):
        self.redis = redis.StrictRedis.from_url(url)

    def _get_stats(self, project, precision):
        current = datetime.datetime.utcnow()
        keys = [
            "downloads:{}:{}:{}".format(
                precision.type,
                (
                    (current - datetime.timedelta(**{precision.delta: x}))
                    .strftime(precision.format)
                ),
                project,
            )
            for x in range(precision.num)
        ]
        return sum(
            [int(x) for x in self.redis.mget(*keys) if x is not None]
        )

    def get_daily_stats(self, project):
        """
        Return the daily download counts for the given project.
        """
        return self._get_stats(project, _PRECISIONS["daily"])

    def get_weekly_stats(self, project):
        """
        Return the weekly download counts for the given project.
        """
        return self._get_stats(project, _PRECISIONS["weekly"])

    def get_monthly_stats(self, project):
        """
        Return the monthly download counts for the given project.
        """
        return self._get_stats(project, _PRECISIONS["monthly"])


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

    def __init__(self, bucket):
        self.bucket = bucket

    @classmethod
    def create_service(cls, context, request):
        session = request.find_service(name="aws.session")
        s3 = session.resource("s3")
        bucket = s3.Bucket(request.registry.settings["files.bucket"])
        return cls(bucket)

    def get(self, path):
        try:
            return self.bucket.Object(path).get()["Body"]
        except botocore.exceptions.ClientError as exc:
            if exc.response["Error"]["Code"] != "NoSuchKey":
                raise
            raise FileNotFoundError("No such key: {!r}".format(path)) from None

    def store(self, path, file_path, *, meta=None):
        extra_args = {}

        if meta is not None:
            extra_args["Metadata"] = meta

        self.bucket.upload_file(file_path, path, ExtraArgs=extra_args)
