# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse.rate_limiting.headers import (
    RateLimitSnapshot,
    rate_limit_headers_tween_factory,
    record_rate_limit,
)
from warehouse.rate_limiting.interfaces import WindowStats


class TestRecordRateLimit:
    def test_records_snapshot_when_stats_available(self):
        stats = [
            WindowStats(amount=5, window_seconds=1, remaining=3, resets_in_seconds=0)
        ]
        limiter = pretend.stub(get_window_stats=pretend.call_recorder(lambda *a: stats))
        request = pretend.stub(__dict__={})

        record_rate_limit(
            request, "search", limiter, identifiers=("1.2.3.4",), partition_key="ip"
        )

        assert limiter.get_window_stats.calls == [pretend.call("1.2.3.4")]
        assert request.__dict__["_rate_limit_snapshots"] == [
            RateLimitSnapshot(name="search", partition_key="ip", stats=stats)
        ]

    def test_skips_when_no_stats(self):
        # When backing storage is unavailable the limiter returns []; we
        # should record nothing rather than emitting empty headers.
        limiter = pretend.stub(get_window_stats=lambda *a: [])
        request = pretend.stub(__dict__={})

        record_rate_limit(
            request, "search", limiter, identifiers=("1.2.3.4",), partition_key="ip"
        )

        assert "_rate_limit_snapshots" not in request.__dict__

    def test_appends_multiple_snapshots(self):
        limiter1 = pretend.stub(
            get_window_stats=lambda *a: [
                WindowStats(
                    amount=5, window_seconds=1, remaining=4, resets_in_seconds=0
                )
            ]
        )
        limiter2 = pretend.stub(
            get_window_stats=lambda *a: [
                WindowStats(
                    amount=10, window_seconds=60, remaining=9, resets_in_seconds=0
                )
            ]
        )
        request = pretend.stub(__dict__={})

        record_rate_limit(
            request, "search", limiter1, identifiers=("ip",), partition_key="ip"
        )
        record_rate_limit(
            request, "search.user", limiter2, identifiers=("u",), partition_key="user"
        )

        snapshots = request.__dict__["_rate_limit_snapshots"]
        assert [s.name for s in snapshots] == ["search", "search.user"]


class TestRateLimitHeadersTween:
    def test_emits_headers_for_recorded_snapshots(self):
        response = pretend.stub(headers={})
        handler = pretend.call_recorder(lambda req: response)
        request = pretend.stub(
            _rate_limit_snapshots=[
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
        )

        tween = rate_limit_headers_tween_factory(handler, pretend.stub())
        result = tween(request)

        assert result is response
        assert response.headers["RateLimit-Policy"] == '"search";q=5;w=1;pk=:ip:'
        assert response.headers["RateLimit"] == '"search";r=3;t=1'

    def test_no_headers_without_snapshots(self):
        response = pretend.stub(headers={})
        handler = lambda req: response  # noqa: E731
        request = pretend.stub()

        tween = rate_limit_headers_tween_factory(handler, pretend.stub())
        tween(request)

        assert response.headers == {}

    def test_no_headers_when_snapshots_list_empty(self):
        response = pretend.stub(headers={})
        handler = lambda req: response  # noqa: E731
        request = pretend.stub(_rate_limit_snapshots=[])

        tween = rate_limit_headers_tween_factory(handler, pretend.stub())
        tween(request)

        assert response.headers == {}

    def test_compound_policy_indexes_each_window(self):
        # When a single limiter has multiple policies (e.g., "5 per minute,
        # 50 per hour"), we suffix each with its index so RateLimit-Policy
        # entries remain unique.
        response = pretend.stub(headers={})
        handler = lambda req: response  # noqa: E731
        request = pretend.stub(
            _rate_limit_snapshots=[
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
        )

        tween = rate_limit_headers_tween_factory(handler, pretend.stub())
        tween(request)

        assert response.headers["RateLimit-Policy"] == (
            '"2fa.user-0";q=5;w=300;pk=:user:, "2fa.user-1";q=50;w=3600;pk=:user:'
        )
        assert response.headers["RateLimit"] == (
            '"2fa.user-0";r=2;t=180, "2fa.user-1";r=47;t=3000'
        )

    def test_multiple_partitions_concatenate(self):
        response = pretend.stub(headers={})
        handler = lambda req: response  # noqa: E731
        request = pretend.stub(
            _rate_limit_snapshots=[
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
        )

        tween = rate_limit_headers_tween_factory(handler, pretend.stub())
        tween(request)

        assert response.headers["RateLimit-Policy"] == (
            '"search";q=5;w=1;pk=:ip:, "search.global";q=1000;w=60;pk=:global:'
        )
        assert response.headers["RateLimit"] == (
            '"search";r=0;t=1, "search.global";r=900;t=30'
        )
