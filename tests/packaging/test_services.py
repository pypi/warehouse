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

import freezegun
import pretend
import pytest
import redis

from zope.interface.verify import verifyClass

from warehouse.packaging.interfaces import IDownloadStatService
from warehouse.packaging.services import RedisDownloadStatService


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
