# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing

import orjson
import redis

from zope.interface import implementer

from warehouse.cache.interfaces import IQueryResultsCache

if typing.TYPE_CHECKING:
    from pyramid.request import Request


@implementer(IQueryResultsCache)
class RedisQueryResults:
    """
    A Redis-based query results cache.

    Anything using this service must assume that the key results may be empty,
    and handle the case where the key is not found in the cache.

    The key is a string, and the value is a JSON-serialized object as a string.
    """

    def __init__(self, redis_client):
        self.redis_client = redis_client

    @classmethod
    def create_service(cls, _context, request: Request) -> RedisQueryResults:
        redis_url = request.registry.settings["db_results_cache.url"]
        redis_client = redis.StrictRedis.from_url(redis_url)
        return cls(redis_client)

    def get(self, key: str) -> list | dict | None:
        """Get a cached result by key."""
        result = self.redis_client.get(key)
        # deserialize the value as a JSON object
        return orjson.loads(result) if result else None

    def set(self, key: str, value) -> None:
        """Set a cached result by key."""
        # serialize the value as a JSON string
        value = orjson.dumps(value)
        self.redis_client.set(key, value)
