# SPDX-License-Identifier: Apache-2.0

import datetime as dt

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

    def test_error(self, mocker, metrics):
        limiter = RateLimiter(
            storage.MemoryStorage(),
            "1 per minute",
            identifiers=["foo"],
            metrics=metrics,
        )
        for name in ("hit", "test", "get_window_stats"):
            mocker.patch.object(
                limiter._window, name, autospec=True, side_effect=redis.ConnectionError
            )
        mocker.patch.object(
            limiter._storage, "clear", autospec=True, side_effect=redis.ConnectionError
        )

        assert limiter.test("foo")
        assert limiter.hit("foo")
        assert limiter.clear("foo") is None
        assert limiter.resets_in("foo") is None
        assert limiter.get_window_stats("foo") == []

        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.ratelimiter.error", tags=["call:test"]),
            mocker.call("warehouse.ratelimiter.error", tags=["call:hit"]),
            mocker.call("warehouse.ratelimiter.error", tags=["call:clear"]),
            mocker.call("warehouse.ratelimiter.error", tags=["call:resets_in"]),
            mocker.call("warehouse.ratelimiter.error", tags=["call:get_window_stats"]),
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

        assert limiter.resets_in("foo") > dt.timedelta(seconds=0)
        assert limiter.resets_in("foo") < dt.timedelta(seconds=60)

    def test_get_window_stats(self, metrics):
        limiter = RateLimiter(
            storage.MemoryStorage(),
            "2 per minute; 10 per hour",
            metrics=metrics,
        )

        # Untouched: full quota remaining; resets_in is clamped to >= 0.
        stats = limiter.get_window_stats("foo")
        assert len(stats) == 2
        assert stats[0].amount == 2
        assert stats[0].window_seconds == 60
        assert stats[0].remaining == 2
        assert stats[0].resets_in_seconds >= 0
        assert stats[1].amount == 10
        assert stats[1].window_seconds == 3600
        assert stats[1].remaining == 10
        assert stats[1].resets_in_seconds >= 0

        # Exhaust the per-minute window; remaining drops, reset pending.
        while limiter.hit("foo"):
            pass

        stats = limiter.get_window_stats("foo")
        assert stats[0].remaining == 0
        assert 0 < stats[0].resets_in_seconds <= 60
        assert stats[1].remaining == 8

    def test_resets_in_expired(self, mocker, metrics):
        limiter = RateLimiter(
            storage.MemoryStorage(),
            "1 per minute; 1 per hour; 1 per day",
            metrics=metrics,
        )

        current = dt.datetime.now(tz=dt.UTC)
        get_window_stats = mocker.patch.object(
            limiter._window,
            "get_window_stats",
            autospec=True,
            side_effect=[
                (0, 0),
                ((current + dt.timedelta(seconds=60)).timestamp(), 0),
                ((current + dt.timedelta(seconds=5)).timestamp(), 0),
            ],
        )

        resets_in = limiter.resets_in("foo")

        assert resets_in > dt.timedelta(seconds=0)
        assert resets_in <= dt.timedelta(seconds=5)
        assert [
            (limit.amount, limit.get_expiry(), identifier)
            for limit, identifier in (
                call.args for call in get_window_stats.call_args_list
            )
        ] == [(1, 60, "foo"), (1, 3600, "foo"), (1, 86400, "foo")]

    def test_override_returns_sibling(self, metrics):
        backend = storage.MemoryStorage()
        limiter = RateLimiter(
            backend, "1 per minute", identifiers=["foo"], metrics=metrics
        )

        sibling = limiter.override("100 per minute")

        assert sibling is not limiter
        assert isinstance(sibling, RateLimiter)
        # The override has to meter the same bucket, not a fresh namespace.
        assert sibling._identifiers == ["foo"]
        assert sibling.test("bar")
        for _ in range(50):
            assert sibling.hit("bar")
        assert sibling.test("bar")

    def test_override_uses_a_separate_window(self, metrics):
        """The amount is part of the storage key, so the override starts fresh."""
        backend = storage.MemoryStorage()
        limiter = RateLimiter(
            backend, "1 per minute", identifiers=["foo"], metrics=metrics
        )

        assert limiter.hit("bar")
        # Exhausted under the default limit.
        assert not limiter.test("bar")

        assert limiter.override("5 per minute").test("bar")

    def test_override_falsy_returns_self(self, metrics):
        limiter = RateLimiter(
            storage.MemoryStorage(),
            "1 per minute",
            identifiers=["foo"],
            metrics=metrics,
        )
        assert limiter.override(None) is limiter
        assert limiter.override("") is limiter

    def test_override_invalid_string_returns_self(self, metrics):
        limiter = RateLimiter(
            storage.MemoryStorage(),
            "1 per minute",
            identifiers=["foo"],
            metrics=metrics,
        )

        assert limiter.override("not a rate limit") is limiter
        metrics.increment.assert_called_once_with(
            "warehouse.ratelimiter.invalid_override",
            tags=["identifiers:foo"],
        )


class TestDummyRateLimiter:
    def test_basic(self):
        limiter = DummyRateLimiter()

        assert limiter.test()
        assert limiter.hit()
        assert limiter.clear() is None
        assert limiter.resets_in() is None
        assert limiter.get_window_stats() == []
        assert limiter.override("100 per minute") is limiter


class TestRateLimit:
    def test_basic(self, mocker, pyramid_request):
        """The default limiter_class builds a real RateLimiter."""
        pyramid_request.registry["ratelimiter.storage"] = storage.MemoryStorage()

        result = RateLimit("1 per 5 minutes", identifiers=["foo"])(
            mocker.sentinel.context, pyramid_request
        )

        assert isinstance(result, RateLimiter)

    def test_limiter_class(self, mocker, pyramid_request, metrics):
        storage_ = storage.MemoryStorage()
        pyramid_request.registry["ratelimiter.storage"] = storage_
        limiter_class = mocker.create_autospec(RateLimiter)

        result = RateLimit(
            "1 per 5 minutes", identifiers=["foo"], limiter_class=limiter_class
        )(mocker.sentinel.context, pyramid_request)

        assert result is limiter_class.return_value
        limiter_class.assert_called_once_with(
            storage_, limit="1 per 5 minutes", identifiers=["foo"], metrics=metrics
        )

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


def test_includeme(mocker, pyramid_config):
    pyramid_config.registry.settings["ratelimit.url"] = "memory://"
    add_directive = mocker.spy(pyramid_config, "add_directive")
    add_tween = mocker.spy(pyramid_config, "add_tween")

    rate_limiting.includeme(pyramid_config)

    add_directive.assert_called_once_with(
        "register_rate_limiter", rate_limiting._register_rate_limiter
    )
    add_tween.assert_called_once_with(
        "warehouse.rate_limiting.headers.rate_limit_headers_tween_factory"
    )
    assert isinstance(
        pyramid_config.registry["ratelimiter.storage"], storage.MemoryStorage
    )


def test_register_rate_limiter_directive(mocker, pyramid_config):
    pyramid_config.include("pyramid_services")
    register_service_factory = mocker.spy(pyramid_config, "register_service_factory")

    rate_limiting._register_rate_limiter(
        pyramid_config, "10 per minute", "test.limiter"
    )

    register_service_factory.assert_called_once_with(
        RateLimit("10 per minute", identifiers=["test.limiter"]),
        rate_limiting.IRateLimiter,
        name="test.limiter",
    )
