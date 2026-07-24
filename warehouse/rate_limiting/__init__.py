# SPDX-License-Identifier: Apache-2.0

import functools
import logging

from datetime import UTC, datetime

import redis

from limits import parse_many
from limits.storage import storage_from_string
from limits.strategies import MovingWindowRateLimiter
from more_itertools import first_true
from zope.interface import implementer

from warehouse.metrics import IMetricsService
from warehouse.rate_limiting.interfaces import IRateLimiter, WindowStats

logger = logging.getLogger(__name__)


def _return_on_exception(rvalue, *exceptions):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            try:
                return fn(self, *args, **kwargs)
            except exceptions as exc:
                logger.warning("Error computing rate limits: %r", exc)
                self._metrics.increment(
                    "warehouse.ratelimiter.error", tags=[f"call:{fn.__name__}"]
                )
                return rvalue

        return wrapper

    return deco


@implementer(IRateLimiter)
class RateLimiter:
    def __init__(self, storage, limit, *, identifiers=None, metrics):
        if identifiers is None:
            identifiers = []

        self._storage = storage
        self._window = MovingWindowRateLimiter(storage)
        self._limits = parse_many(limit)
        self._identifiers = identifiers
        self._metrics = metrics

    def _get_identifiers(self, identifiers):
        return [str(i) for i in list(self._identifiers) + list(identifiers)]

    @_return_on_exception(True, redis.RedisError)
    def test(self, *identifiers):
        return all(
            self._window.test(limit, *self._get_identifiers(identifiers))
            for limit in self._limits
        )

    @_return_on_exception(True, redis.RedisError)
    def hit(self, *identifiers):
        return all(
            self._window.hit(limit, *self._get_identifiers(identifiers))
            for limit in self._limits
        )

    @_return_on_exception(None, redis.RedisError)
    def clear(self, *identifiers):
        for limit in self._limits:
            self._storage.clear(limit.key_for(*self._get_identifiers(identifiers)))

    def override(self, limit_string):
        """
        Return a new RateLimiter using ``limit_string``, or self if it is
        falsy.

        A malformed ``limit_string`` (e.g. a bad per-entity override stored
        in the database) falls back to self rather than failing the request.
        """
        if not limit_string:
            return self

        try:
            return RateLimiter(
                self._storage,
                limit_string,
                identifiers=self._identifiers,
                metrics=self._metrics,
            )
        except ValueError:
            logger.warning(
                "Invalid rate limit override %r; using default", limit_string
            )
            self._metrics.increment(
                "warehouse.ratelimiter.invalid_override",
                tags=[f"identifiers:{','.join(self._identifiers)}"],
            )
            return self

    @_return_on_exception(None, redis.RedisError)
    def resets_in(self, *identifiers):
        resets = []
        for limit in self._limits:
            resets_at, remaining = self._window.get_window_stats(
                limit, *self._get_identifiers(identifiers)
            )

            # If this limit has any remaining limits left, then we will skip it
            # since it doesn't need reset.
            if remaining > 0:
                continue

            current = datetime.now(tz=UTC)
            reset = datetime.fromtimestamp(resets_at, tz=UTC)

            # If our current datetime is either greater than or equal to when
            # the limit resets, then we will skip it since it has either
            # already reset, or it is resetting now.
            if current >= reset:
                continue

            # Add a timedelta that represents how long until this limit resets.
            resets.append(reset - current)

        # If we have any resets, then we'll go through and find whichever one
        # is going to reset soonest and use that as our hint for when this
        # limit might be available again.
        return first_true(sorted(resets))

    @_return_on_exception([], redis.RedisError)
    def get_window_stats(self, *identifiers):
        stats = []
        now = datetime.now(tz=UTC)
        for limit in self._limits:
            resets_at, remaining = self._window.get_window_stats(
                limit, *self._get_identifiers(identifiers)
            )
            reset = datetime.fromtimestamp(resets_at, tz=UTC)
            resets_in_seconds = max(0, int((reset - now).total_seconds()))
            stats.append(
                WindowStats(
                    amount=limit.amount,
                    window_seconds=limit.get_expiry(),
                    remaining=remaining,
                    resets_in_seconds=resets_in_seconds,
                )
            )
        return stats


@implementer(IRateLimiter)
class DummyRateLimiter:
    def test(self, *identifiers):
        return True

    def hit(self, *identifiers):
        return True

    def clear(self, *identifiers):
        return None

    def override(self, limit_string):
        return self

    def resets_in(self, *identifiers):
        return None

    def get_window_stats(self, *identifiers):
        return []


class RateLimit:
    def __init__(self, limit, identifiers=None, limiter_class=RateLimiter):
        self.limit = limit
        self.identifiers = identifiers
        self.limiter_class = limiter_class

    def __call__(self, context, request):
        return self.limiter_class(
            request.registry["ratelimiter.storage"],
            limit=self.limit,
            identifiers=self.identifiers,
            metrics=request.find_service(IMetricsService, context=None),
        )

    def __repr__(self):
        return (
            f'RateLimit("{self.limit}", identifiers={self.identifiers}, '
            f"limiter_class={self.limiter_class})"
        )

    def __eq__(self, other):
        if not isinstance(other, RateLimit):
            return NotImplemented

        return (self.limit, self.identifiers, self.limiter_class) == (
            other.limit,
            other.identifiers,
            other.limiter_class,
        )


def _register_rate_limiter(config, limit_string, name):
    """Register a rate limiter service with identifiers matching the service name."""
    config.register_service_factory(
        RateLimit(limit_string, identifiers=[name]),
        IRateLimiter,
        name=name,
    )


def includeme(config):
    config.add_directive("register_rate_limiter", _register_rate_limiter)
    config.registry["ratelimiter.storage"] = storage_from_string(
        config.registry.settings["ratelimit.url"]
    )
    config.add_tween("warehouse.rate_limiting.headers.rate_limit_headers_tween_factory")
