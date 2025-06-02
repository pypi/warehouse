# SPDX-License-Identifier: Apache-2.0

import datetime
import uuid

import pretend

from zope.interface.verify import verifyClass

from warehouse.cache.interfaces import IQueryResultsCache
from warehouse.cache.services import RedisQueryResults


class TestRedisQueryResults:
    def test_interface_matches(self):
        assert verifyClass(IQueryResultsCache, RedisQueryResults)

    def test_create_service(self):
        request = pretend.stub(
            registry=pretend.stub(settings={"db_results_cache.url": "redis://"})
        )
        # Create the service
        service = RedisQueryResults.create_service(None, request)

        assert isinstance(service, RedisQueryResults)

    def test_get_missing(self, query_results_cache_service):
        # Attempt to get a value that doesn't exist in the cache
        result = query_results_cache_service.get("missing_key")

        assert result is None

    def test_set_get_simple(self, query_results_cache_service):
        # Set a value in the cache
        query_results_cache_service.set("test_key", {"foo": "bar"})

        # Get the value from the cache
        result = query_results_cache_service.get("test_key")

        assert result == {"foo": "bar"}

    def test_set_get_complex(self, query_results_cache_service):
        # Construct a complex object to store in the cache
        obj = {
            "uuid": uuid.uuid4(),
            "datetime": datetime.datetime.now(),
            "list": [1, 2, 3],
            "dict": {"key": "value"},
        }
        # Set the complex object in the cache
        query_results_cache_service.set("complex_key", obj)

        # Get the complex object from the cache
        result = query_results_cache_service.get("complex_key")

        # Check that the result is the "same" as the original object, except
        # for the UUID and datetime, which are now strings
        assert result["list"] == obj["list"]
        assert result["dict"] == obj["dict"]
        assert result["uuid"] == str(obj["uuid"])
        assert result["datetime"] == obj["datetime"].isoformat()
        assert isinstance(result["list"], list)
        assert isinstance(result["dict"], dict)
        assert isinstance(result["uuid"], str)
        assert isinstance(result["datetime"], str)
