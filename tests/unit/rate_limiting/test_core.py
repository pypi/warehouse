# SPDX-License-Identifier: Apache-2.0

import datetime

import pretend
import redis

from limits import storage

from warehouse import rate_limiting
from warehouse.rate_limiting import DummyRateLimiter, RateLimit, RateLimiter


class TestRateLimiter:
    def test_basic(self, metrics):
        limiter = RateLimiter(
            storage.MemoryStorage(),
            "1 per minute",
            identifiers=["foo"],
            metrics=metrics,
        )

        assert limiter.test("foo")
        assert limiter.test("bar")

        while limiter.hit("bar"):
            pass

        assert limiter.test("foo")
        assert not limiter.test("bar")

    def test_error(self, metrics):
        limiter = RateLimiter(
            storage.MemoryStorage(),
            "1 per minute",
            identifiers=["foo"],
            metrics=metrics,
        )

        def raiser(*args, **kwargs):
            raise redis.ConnectionError()

        limiter._window = pretend.stub(hit=raiser, test=raiser, get_window_stats=raiser)

        assert limiter.test("foo")
        assert limiter.hit("foo")
        assert limiter.resets_in("foo") is None

        assert metrics.increment.calls == [
            pretend.call("warehouse.ratelimiter.error", tags=["call:test"]),
            pretend.call("warehouse.ratelimiter.error", tags=["call:hit"]),
            pretend.call("warehouse.ratelimiter.error", tags=["call:resets_in"]),
        ]

    def test_namespacing(self, metrics):
        storage_ = storage.MemoryStorage()
        limiter1 = RateLimiter(
            storage_, "1 per minute", identifiers=["foo"], metrics=metrics
        )
        limiter2 = RateLimiter(storage_, "1 per minute", metrics=metrics)

        assert limiter1.test("bar")
        assert limiter2.test("bar")

        while limiter1.hit("bar"):
            pass

        assert limiter2.test("bar")
        assert not limiter1.test("bar")

    def test_clear(self, metrics):
        limiter = RateLimiter(storage.MemoryStorage(), "1 per minute", metrics=metrics)

        assert limiter.test("foo")

        while limiter.hit("foo"):
            pass

        assert not limiter.test("foo")

        limiter.clear("foo")

        assert limiter.test("foo")

    def test_resets_in(self, metrics):
        limiter = RateLimiter(storage.MemoryStorage(), "1 per minute", metrics=metrics)

        assert limiter.resets_in("foo") is None

        while limiter.hit("foo"):
            pass

        assert limiter.resets_in("foo") > datetime.timedelta(seconds=0)
        assert limiter.resets_in("foo") < datetime.timedelta(seconds=60)

    def test_resets_in_expired(self, metrics):
        limiter = RateLimiter(
            storage.MemoryStorage(),
            "1 per minute; 1 per hour; 1 per day",
            metrics=metrics,
        )

        current = datetime.datetime.now(tz=datetime.UTC)
        stats = iter(
            [
                (0, 0),
                ((current + datetime.timedelta(seconds=60)).timestamp(), 0),
                ((current + datetime.timedelta(seconds=5)).timestamp(), 0),
            ]
        )

        limiter._window = pretend.stub(get_window_stats=lambda L, *a: next(stats))

        resets_in = limiter.resets_in("foo")

        assert resets_in > datetime.timedelta(seconds=0)
        assert resets_in <= datetime.timedelta(seconds=5)


class TestDummyRateLimiter:
    def test_basic(self):
        limiter = DummyRateLimiter()

        assert limiter.test()
        assert limiter.hit()
        assert limiter.clear() is None
        assert limiter.resets_in() is None


class TestRateLimit:
    def test_basic(self, pyramid_request, metrics):
        limiter_obj = pretend.stub()
        limiter_class = pretend.call_recorder(lambda *a, **kw: limiter_obj)

        context = pretend.stub()
        pyramid_request.registry["ratelimiter.storage"] = pretend.stub()

        result = RateLimit(
            "1 per 5 minutes", identifiers=["foo"], limiter_class=limiter_class
        )(context, pyramid_request)

        assert result is limiter_obj
        assert limiter_class.calls == [
            pretend.call(
                pyramid_request.registry["ratelimiter.storage"],
                limit="1 per 5 minutes",
                identifiers=["foo"],
                metrics=metrics,
            )
        ]

    def test_repr(self):
        assert repr(RateLimit("one per hour")) == (
            'RateLimit("one per hour", identifiers=None, '
            "limiter_class=<class 'warehouse.rate_limiting.RateLimiter'>)"
        )

    def test_eq(self):
        assert RateLimit("1 per 5 minutes", identifiers=["foo"]) == RateLimit(
            "1 per 5 minutes", identifiers=["foo"]
        )
        assert RateLimit("1 per 5 minutes", identifiers=["foo"]) != RateLimit(
            "1 per 5 minutes", identifiers=["bar"]
        )
        assert RateLimit("1 per 5 minutes", identifiers=["foo"]) != object()


def test_includeme():
    registry = {}
    config = pretend.stub(
        add_directive=pretend.call_recorder(lambda name, func: None),
        registry=pretend.stub(
            settings={"ratelimit.url": "memory://"}, __setitem__=registry.__setitem__
        ),
    )

    rate_limiting.includeme(config)

    assert config.add_directive.calls == [
        pretend.call("register_rate_limiter", rate_limiting._register_rate_limiter)
    ]
    assert isinstance(registry["ratelimiter.storage"], storage.MemoryStorage)


def test_register_rate_limiter_directive():
    config = pretend.stub(
        register_service_factory=pretend.call_recorder(
            lambda factory, iface, name: None
        ),
    )

    rate_limiting._register_rate_limiter(config, "10 per minute", "test.limiter")

    assert len(config.register_service_factory.calls) == 1
    call = config.register_service_factory.calls[0]
    assert call.kwargs["name"] == "test.limiter"
    assert call.args[1] is rate_limiting.IRateLimiter
    # Verify the factory is a RateLimit with correct parameters
    factory = call.args[0]
    assert isinstance(factory, RateLimit)
    assert factory.limit == "10 per minute"
    assert factory.identifiers == ["test.limiter"]
