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

import functools
import logging

from datetime import datetime, timezone

import redis

from first import first
from limits import parse_many
from limits.strategies import MovingWindowRateLimiter
from limits.storage import storage_from_string
from zope.interface import implementer

from warehouse.metrics import IMetricsService
from warehouse.rate_limiting.interfaces import IRateLimiter


logger = logging.getLogger(__name__)


def _return_on_exception(rvalue, *exceptions):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            try:
                return fn(self, *args, **kwargs)
            except exceptions as exc:
                logging.warning("Error computing rate limits: %r", exc)
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

        self._window = MovingWindowRateLimiter(storage)
        self._limits = parse_many(limit)
        self._identifiers = identifiers
        self._metrics = metrics

    def _get_identifiers(self, identifiers):
        return [str(i) for i in list(self._identifiers) + list(identifiers)]

    @_return_on_exception(True, redis.RedisError)
    def test(self, *identifiers):
        return all(
            [
                self._window.test(limit, *self._get_identifiers(identifiers))
                for limit in self._limits
            ]
        )

    @_return_on_exception(True, redis.RedisError)
    def hit(self, *identifiers):
        return all(
            [
                self._window.hit(limit, *self._get_identifiers(identifiers))
                for limit in self._limits
            ]
        )

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

            current = datetime.now(tz=timezone.utc)
            reset = datetime.fromtimestamp(resets_at, tz=timezone.utc)

            # If our current datetime is either greater than or equal to when
            # the limit resets, then we will skipp it since it has either
            # already reset, or it is resetting now.
            if current >= reset:
                continue

            # Add a timedelta that represents how long until this limit resets.
            resets.append(reset - current)

        # If we have any resets, then we'll go through and find whichever one
        # is going to reset soonest and use that as our hint for when this
        # limit might be available again.
        return first(sorted(resets))


@implementer(IRateLimiter)
class DummyRateLimiter:
    def test(self, *identifiers):
        return True

    def hit(self, *identifiers):
        return True

    def resets_in(self, *identifiers):
        return None


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

    def __eq__(self, other):
        if not isinstance(other, RateLimit):
            return NotImplemented

        return (self.limit, self.identifiers, self.limiter_class) == (
            other.limit,
            other.identifiers,
            other.limiter_class,
        )


def includeme(config):
    config.registry["ratelimiter.storage"] = storage_from_string(
        config.registry.settings["ratelimit.url"]
    )
