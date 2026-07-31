# SPDX-License-Identifier: Apache-2.0

import json

import redis

from warehouse.legacy.api.xmlrpc.cache.interfaces import CacheError

DEFAULT_EXPIRES = 86400


class StubMetricReporter:
    def increment(self, metric_name):
        return


class RedisLru:
    """
    Redis backed LRU cache for functions which return an object which
    can survive json.dumps() and json.loads() intact.

    Note the "intact" constraint is narrower than it looks: tuples come back as
    lists, scalar dict keys are coerced to strings without complaint, and
    anything the stdlib encoder cannot handle (datetime, date, time, UUID,
    Decimal) raises TypeError on write. See the caveats documented on
    `xmlrpc_cache_by_project` in warehouse/legacy/api/xmlrpc/views.py.
    """

    def __init__(self, conn, name="lru", expires=None, metric_reporter=None):
        """
        conn:            Redis Connection Object
        name:            Prefix for all keys in the cache
        expires:         Default expiration
        metric_reporter: Object implementing an `increment(<string>)` method
        """
        self.conn = conn
        self.name = name
        self.expires = expires or DEFAULT_EXPIRES
        if callable(getattr(metric_reporter, "increment", None)):
            self.metric_reporter = metric_reporter
        else:
            self.metric_reporter = StubMetricReporter()

    def format_key(self, func_name, tag):
        if tag is not None and tag != "None":
            return f"{self.name}:{tag}:{func_name}"
        return f"{self.name}:tag:{func_name}"

    def get(self, func_name, key, tag):
        try:
            value = self.conn.hget(self.format_key(func_name, tag), str(key))
        except redis.exceptions.RedisError, redis.exceptions.ConnectionError:
            self.metric_reporter.increment(f"warehouse.{self.name}.cache.error")
            return None
        if value:
            self.metric_reporter.increment(f"warehouse.{self.name}.cache.hit")
            value = json.loads(value)
        return value

    def add(self, func_name, key, value, tag, expires):
        try:
            self.metric_reporter.increment(f"warehouse.{self.name}.cache.miss")
            pipeline = self.conn.pipeline()
            pipeline.hset(
                self.format_key(func_name, tag),
                str(key),
                # `ensure_ascii` is left at its default so the serializer output is
                # always encodable: redis-py raises UnicodeEncodeError on lone
                # surrogates, which is not a RedisError and escapes the handler below.
                json.dumps(value, separators=(",", ":")),
            )
            ttl = expires or self.expires
            pipeline.expire(self.format_key(func_name, tag), ttl)
            pipeline.execute()
            return value
        except redis.exceptions.RedisError, redis.exceptions.ConnectionError:
            self.metric_reporter.increment(f"warehouse.{self.name}.cache.error")
            return value

    def purge(self, tag):
        try:
            keys = self.conn.scan_iter(f"{self.name}:{tag}:*", count=1000)
            pipeline = self.conn.pipeline()
            for key in keys:
                pipeline.delete(key)
            pipeline.execute()
            self.metric_reporter.increment(f"warehouse.{self.name}.cache.purge")
        except redis.exceptions.RedisError, redis.exceptions.ConnectionError:
            self.metric_reporter.increment(f"warehouse.{self.name}.cache.error")
            raise CacheError

    def fetch(self, func, args, kwargs, key, tag, expires):
        # `get` returns None for both a miss and a Redis error, so compare against
        # None rather than testing truthiness: an empty list or dict is a real hit.
        # Treating it as a miss counts the request as both a hit and a miss and
        # re-runs the query on every call.
        value = self.get(func.__name__, str(key), str(tag))
        if value is not None:
            return value
        return self.add(
            func.__name__, str(key), func(*args, **kwargs), str(tag), expires
        )
