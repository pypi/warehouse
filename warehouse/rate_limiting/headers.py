# SPDX-License-Identifier: Apache-2.0

"""
RateLimit and RateLimit-Policy response headers.

Headers follow the syntax of draft-ietf-httpapi-ratelimit-headers-10. The
draft is currently expired but the most recent IETF working-group form, so we
emit headers as advisory and may revise the syntax once the draft is revived
or published as an RFC.

See: https://www.ietf.org/archive/id/draft-ietf-httpapi-ratelimit-headers-10.html
"""

from dataclasses import dataclass
from typing import Literal

from warehouse.rate_limiting.interfaces import IRateLimiter, WindowStats

PartitionKey = Literal["ip", "user", "global", "organization"]


@dataclass(frozen=True)
class RateLimitSnapshot:
    name: str
    partition_key: PartitionKey
    stats: list[WindowStats]


def record_rate_limit(
    request,
    name: str,
    limiter: IRateLimiter,
    *,
    identifiers,
    partition_key: PartitionKey,
) -> None:
    """
    Capture a snapshot of the limiter's current state for the given identifiers
    so the egress tween can render RateLimit / RateLimit-Policy headers.

    Safe to call multiple times per request; each call appends a snapshot.
    `partition_key` is an opaque label (e.g. "ip", "user") describing what the
    limiter is keyed on — never the raw identifier value.
    """
    stats = limiter.get_window_stats(*identifiers)
    if not stats:
        return
    snapshots = request.__dict__.setdefault("_rate_limit_snapshots", [])
    snapshots.append(
        RateLimitSnapshot(name=name, partition_key=partition_key, stats=stats)
    )


def _policy_name(snap: RateLimitSnapshot, idx: int) -> str:
    return snap.name if len(snap.stats) == 1 else f"{snap.name}-{idx}"


def _format_policy(snapshots: list[RateLimitSnapshot]) -> str:
    parts = []
    for snap in snapshots:
        for idx, s in enumerate(snap.stats):
            parts.append(
                f'"{_policy_name(snap, idx)}";q={s.amount};w={s.window_seconds};'
                f"pk=:{snap.partition_key}:"
            )
    return ", ".join(parts)


def _format_state(snapshots: list[RateLimitSnapshot]) -> str:
    parts = []
    for snap in snapshots:
        for idx, s in enumerate(snap.stats):
            parts.append(
                f'"{_policy_name(snap, idx)}";r={s.remaining};t={s.resets_in_seconds}'
            )
    return ", ".join(parts)


def rate_limit_headers_tween_factory(handler, registry):
    def rate_limit_headers_tween(request):
        response = handler(request)
        snapshots = getattr(request, "_rate_limit_snapshots", None)
        if snapshots:
            response.headers["RateLimit-Policy"] = _format_policy(snapshots)
            response.headers["RateLimit"] = _format_state(snapshots)
        return response

    return rate_limit_headers_tween
