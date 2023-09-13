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
from limits.storage import storage_from_string
from limits.strategies import MovingWindowRateLimiter
from pyramid.httpexceptions import HTTPTooManyRequests
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
    def clear(self, *identifiers):
        for limit in self._limits:
            self._storage.clear(limit.key_for(*self._get_identifiers(identifiers)))

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

    def clear(self, *identifiers):
        return None

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


def ratelimit_view_deriver(view, info):
    """
    A general-purpose rate limit view deriver based on client's `remote_addr`.
    https://docs.pylonsproject.org/projects/pyramid/en/latest/narr/hooks.html#custom-view-derivers

    Add `ratelimiter="<limit-string>"` to a `@view_config()`. Example:

    ```
    @view_config(
        ...,
        ratelimit="10/second",
    )
    ```
    https://limits.readthedocs.io/en/stable/quickstart.html#rate-limit-string-notation
    """
    limit_str = info.options.get("ratelimit")
    if limit_str:

        def wrapper_view(context, request):
            ratelimiter = request.find_service(
                IRateLimiter, name="rate_limiting.client"
            )
            # TODO: Is this Kosher?
            # Override the default limits with the ones specified in the view
            ratelimiter._limits = parse_many(limit_str)

            metrics = request.find_service(IMetricsService, context=None)

            request_route = request.matched_route.name

            ratelimiter.hit(request.remote_addr)
            if not ratelimiter.test(request.remote_addr):
                metrics.increment(
                    "warehouse.ratelimiter.exceeded",
                    tags=[
                        f"request_route:{request_route}",
                    ],
                )
                message = (
                    "The action could not be performed because there were too "
                    "many requests by the client."
                )
                _resets_in = ratelimiter.resets_in(request.remote_addr)
                if _resets_in is not None:
                    _resets_in = max(1, int(_resets_in.total_seconds()))
                    message += f" Limit may reset in {_resets_in} seconds."
                raise HTTPTooManyRequests(message)

            metrics.increment(
                "warehouse.ratelimiter.hit",
                tags=[
                    f"request_route:{request_route}",
                ],
            )
            return view(context, request)

        return wrapper_view
    return view


ratelimit_view_deriver.options = ("ratelimit",)  # type: ignore[attr-defined]


def includeme(config):
    config.registry["ratelimiter.storage"] = storage_from_string(
        config.registry.settings["ratelimit.url"]
    )

    config.register_service_factory(
        # TODO: What's a good default?
        RateLimit(limit="1/second"),
        IRateLimiter,
        name="rate_limiting.client",
    )

    config.add_view_deriver(ratelimit_view_deriver)
