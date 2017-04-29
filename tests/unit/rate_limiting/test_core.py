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

import datetime

import pretend

from limits import storage

from warehouse import rate_limiting
from warehouse.rate_limiting import RateLimiter, DummyRateLimiter, RateLimit


class TestRateLimiter(object):

    def test_basic(self):
        limiter = RateLimiter(
            storage.MemoryStorage(),
            "1 per minute",
            identifiers=["foo"],
        )

        assert limiter.test("foo")
        assert limiter.test("bar")

        while limiter.hit("bar"):
            pass

        assert limiter.test("foo")
        assert not limiter.test("bar")

    def test_namespacing(self):
        storage_ = storage.MemoryStorage()
        limiter1 = RateLimiter(storage_, "1 per minute", identifiers=["foo"])
        limiter2 = RateLimiter(storage_, "1 per minute")

        assert limiter1.test("bar")
        assert limiter2.test("bar")

        while limiter1.hit("bar"):
            pass

        assert limiter2.test("bar")
        assert not limiter1.test("bar")

    def test_results_in(self):
        limiter = RateLimiter(storage.MemoryStorage(), "1 per minute")

        assert limiter.resets_in("foo") is None

        while limiter.hit("foo"):
            pass

        assert limiter.resets_in("foo") > datetime.timedelta(seconds=0)
        assert limiter.resets_in("foo") < datetime.timedelta(seconds=60)

    def test_results_in_expired(self):
        limiter = RateLimiter(
            storage.MemoryStorage(),
            "1 per minute; 1 per hour; 1 per day",
        )

        current = datetime.datetime.now(tz=datetime.timezone.utc)
        stats = iter([
            (0, 0),
            ((current + datetime.timedelta(seconds=60)).timestamp(), 0),
            ((current + datetime.timedelta(seconds=5)).timestamp(), 0),
        ])

        limiter._window = pretend.stub(
            get_window_stats=lambda l, *a: next(stats),
        )

        resets_in = limiter.resets_in("foo")

        assert resets_in > datetime.timedelta(seconds=0)
        assert resets_in <= datetime.timedelta(seconds=5)


class TestDummyRateLimiter(object):

    def test_basic(self):
        limiter = DummyRateLimiter()

        assert limiter.test()
        assert limiter.hit()
        assert limiter.resets_in() is None


class TestRateLimit(object):

    def test_basic(self):
        limiter_obj = pretend.stub()
        limiter_class = pretend.call_recorder(lambda *a, **kw: limiter_obj)

        context = pretend.stub()
        request = pretend.stub(
            registry={"ratelimiter.storage": pretend.stub()},
        )

        result = RateLimit(
            "1 per 5 minutes",
            identifiers=["foo"],
            limiter_class=limiter_class,
        )(context, request)

        assert result is limiter_obj
        assert limiter_class.calls == [
            pretend.call(
                request.registry["ratelimiter.storage"],
                limit="1 per 5 minutes",
                identifiers=["foo"],
            ),
        ]


def test_includeme():
    registry = {}
    config = pretend.stub(
        registry=pretend.stub(
            settings={"ratelimit.url": "memory://"},
            __setitem__=registry.__setitem__,
        ),
    )

    rate_limiting.includeme(config)

    assert isinstance(registry["ratelimiter.storage"], storage.MemoryStorage)
