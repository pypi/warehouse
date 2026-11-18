# SPDX-License-Identifier: Apache-2.0

import pytest
import redis

from limits import storage
from pyramid.response import Response

from warehouse.rate_limiting import RateLimiter
from warehouse.rate_limiting.headers import (
    RateLimitSnapshot,
    rate_limit_headers_tween_factory,
    record_rate_limit,
)
from warehouse.rate_limiting.interfaces import WindowStats


class TestRecordRateLimit:
    def test_records_snapshot_when_stats_available(self, mocker, pyramid_request):
        stats = [
            WindowStats(amount=5, window_seconds=1, remaining=3, resets_in_seconds=0)
        ]
        limiter = mocker.create_autospec(RateLimiter, instance=True)
        limiter.get_window_stats.return_value = stats

        record_rate_limit(
            pyramid_request,
            "search",
            limiter,
            identifiers=("1.2.3.4",),
            partition_key="ip",
        )

        limiter.get_window_stats.assert_called_once_with("1.2.3.4")
        assert pyramid_request.__dict__["_rate_limit_snapshots"] == [
            RateLimitSnapshot(name="search", partition_key="ip", stats=stats)
        ]

    def test_skips_when_no_stats(self, mocker, pyramid_request, metrics):
        """
        An empty stats list is what RateLimiter returns when its storage (Redis)
        is unavailable, so no snapshot is recorded and no headers are emitted.
        """
        limiter = RateLimiter(storage.MemoryStorage(), "1 per minute", metrics=metrics)
        mocker.patch.object(
            limiter._window,
            "get_window_stats",
            autospec=True,
            side_effect=redis.ConnectionError,
        )

        record_rate_limit(
            pyramid_request,
            "search",
            limiter,
            identifiers=("1.2.3.4",),
            partition_key="ip",
        )

        assert "_rate_limit_snapshots" not in pyramid_request.__dict__
        metrics.increment.assert_called_once_with(
            "warehouse.ratelimiter.error", tags=["call:get_window_stats"]
        )

    def test_appends_multiple_snapshots(self, mocker, pyramid_request):
        limiter1 = mocker.create_autospec(RateLimiter, instance=True)
        limiter1.get_window_stats.return_value = [
            WindowStats(amount=5, window_seconds=1, remaining=4, resets_in_seconds=0)
        ]
        limiter2 = mocker.create_autospec(RateLimiter, instance=True)
        limiter2.get_window_stats.return_value = [
            WindowStats(amount=10, window_seconds=60, remaining=9, resets_in_seconds=0)
        ]

        record_rate_limit(
            pyramid_request, "search", limiter1, identifiers=("ip",), partition_key="ip"
        )
        record_rate_limit(
            pyramid_request,
            "search.user",
            limiter2,
            identifiers=("u",),
            partition_key="user",
        )

        limiter1.get_window_stats.assert_called_once_with("ip")
        limiter2.get_window_stats.assert_called_once_with("u")
        snapshots = pyramid_request.__dict__["_rate_limit_snapshots"]
        assert [s.name for s in snapshots] == ["search", "search.user"]


class TestRateLimitHeadersTween:
    @pytest.fixture
    def handler(self, mocker):
        return mocker.create_autospec(lambda request: None, return_value=Response())

    @pytest.fixture
    def tween(self, handler, pyramid_request):
        return rate_limit_headers_tween_factory(handler, pyramid_request.registry)

    def test_emits_headers_for_recorded_snapshots(
        self, handler, tween, pyramid_request
    ):
        response = handler.return_value
        pyramid_request._rate_limit_snapshots = [
            RateLimitSnapshot(
                name="search",
                partition_key="ip",
                stats=[
                    WindowStats(
                        amount=5,
                        window_seconds=1,
                        remaining=3,
                        resets_in_seconds=1,
                    )
                ],
            ),
        ]

        result = tween(pyramid_request)

        assert result is response
        handler.assert_called_once_with(pyramid_request)
        assert response.headers["RateLimit-Policy"] == '"search";q=5;w=1;pk=:ip:'
        assert response.headers["RateLimit"] == '"search";r=3;t=1'

    def test_no_headers_without_snapshots(self, handler, tween, pyramid_request):
        response = handler.return_value

        assert tween(pyramid_request) is response
        assert response.headers == Response().headers

    def test_no_headers_when_snapshots_list_empty(
        self, handler, tween, pyramid_request
    ):
        response = handler.return_value
        pyramid_request._rate_limit_snapshots = []

        assert tween(pyramid_request) is response
        assert response.headers == Response().headers

    def test_compound_policy_indexes_each_window(self, handler, tween, pyramid_request):
        # When a single limiter has multiple policies (e.g., "5 per minute,
        # 50 per hour"), we suffix each with its index so RateLimit-Policy
        # entries remain unique.
        response = handler.return_value
        pyramid_request._rate_limit_snapshots = [
            RateLimitSnapshot(
                name="2fa.user",
                partition_key="user",
                stats=[
                    WindowStats(
                        amount=5,
                        window_seconds=300,
                        remaining=2,
                        resets_in_seconds=180,
                    ),
                    WindowStats(
                        amount=50,
                        window_seconds=3600,
                        remaining=47,
                        resets_in_seconds=3000,
                    ),
                ],
            )
        ]

        assert tween(pyramid_request) is response

        assert response.headers["RateLimit-Policy"] == (
            '"2fa.user-0";q=5;w=300;pk=:user:, "2fa.user-1";q=50;w=3600;pk=:user:'
        )
        assert response.headers["RateLimit"] == (
            '"2fa.user-0";r=2;t=180, "2fa.user-1";r=47;t=3000'
        )

    def test_multiple_partitions_concatenate(self, handler, tween, pyramid_request):
        response = handler.return_value
        pyramid_request._rate_limit_snapshots = [
            RateLimitSnapshot(
                name="search",
                partition_key="ip",
                stats=[
                    WindowStats(
                        amount=5,
                        window_seconds=1,
                        remaining=0,
                        resets_in_seconds=1,
                    )
                ],
            ),
            RateLimitSnapshot(
                name="search.global",
                partition_key="global",
                stats=[
                    WindowStats(
                        amount=1000,
                        window_seconds=60,
                        remaining=900,
                        resets_in_seconds=30,
                    )
                ],
            ),
        ]

        assert tween(pyramid_request) is response

        assert response.headers["RateLimit-Policy"] == (
            '"search";q=5;w=1;pk=:ip:, "search.global";q=1000;w=60;pk=:global:'
        )
        assert response.headers["RateLimit"] == (
            '"search";r=0;t=1, "search.global";r=900;t=30'
        )
