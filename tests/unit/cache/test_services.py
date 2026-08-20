# SPDX-License-Identifier: Apache-2.0

from zope.interface.verify import verifyClass

from warehouse.cache.interfaces import IQueryResultsCache
from warehouse.cache.services import RedisQueryResults


class TestRedisQueryResults:
    def test_interface_matches(self):
        assert verifyClass(IQueryResultsCache, RedisQueryResults)

    def test_create_service(self, pyramid_request):
        pyramid_request.registry.settings["db_results_cache.url"] = "redis://"
        # Create the service
        service = RedisQueryResults.create_service(None, pyramid_request)

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

    def test_set_get_nested(self, query_results_cache_service):
        obj = {
            "list": [1, 2, 3],
            "dict": {"key": "value"},
        }
        query_results_cache_service.set("complex_key", obj)

        result = query_results_cache_service.get("complex_key")

        assert result == obj
