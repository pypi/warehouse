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

import redis

from zope.interface import implementer

from warehouse.packaging.interfaces import IDownloadStatService


_PRECISION = collections.namedtuple(
    "_PRECISION",
    ["type", "delta", "format", "num"],
)

_PRECISIONS = {
    "daily":  _PRECISION(
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
