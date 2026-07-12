# SPDX-License-Identifier: Apache-2.0

import types

import celery
import pytest
import redis

from pyramid.exceptions import ConfigurationError

import warehouse.legacy.api.xmlrpc.cache

from warehouse.legacy.api.xmlrpc import cache
from warehouse.legacy.api.xmlrpc.cache import (
    NullXMLRPCCache,
    RedisLru,
    RedisXMLRPCCache,
    cached_return_view,
    services,
)
from warehouse.legacy.api.xmlrpc.cache.interfaces import CacheError, IXMLRPCCache


def func_test(arg0, arg1, kwarg0=0, kwarg1=1):
    return [[arg0, arg1], {"kwarg0": kwarg0, "kwarg1": kwarg1}]


class TestXMLRPCCache:
    def test_null_cache(self, mocker):
        service = NullXMLRPCCache("null://", mocker.stub(name="purger"))

        assert service.fetch(
            func_test, (1, 2), {"kwarg0": 3, "kwarg1": 4}, None, None, None
        ) == [[1, 2], {"kwarg0": 3, "kwarg1": 4}]

        assert service.purge(None) is None


class TestRedisXMLRPCCache:
    def test_redis_cache(self, mocker):
        strict_redis = mocker.patch.object(redis, "StrictRedis", autospec=True)
        strict_redis.from_url.return_value = mocker.sentinel.strict_redis_obj

        redis_lru_cls = mocker.patch.object(
            warehouse.legacy.api.xmlrpc.cache, "RedisLru", autospec=True
        )
        redis_lru_obj = redis_lru_cls.return_value

        def fetch_side_effect(func, args, kwargs, key, tag, expires):
            return func(*args, **kwargs)

        redis_lru_obj.fetch.side_effect = fetch_side_effect
        redis_lru_obj.purge.return_value = None

        service = RedisXMLRPCCache("redis://localhost:6379", mocker.stub(name="purger"))

        strict_redis.from_url.assert_called_once_with("redis://localhost:6379", db=0)
        redis_lru_cls.assert_called_once_with(
            mocker.sentinel.strict_redis_obj,
            name="lru",
            expires=None,
            metric_reporter=None,
        )

        assert service.fetch(
            func_test, (1, 2), {"kwarg0": 3, "kwarg1": 4}, None, None, None
        ) == [[1, 2], {"kwarg0": 3, "kwarg1": 4}]

        assert service.purge(None) is None

        redis_lru_obj.fetch.assert_called_once_with(
            func_test, (1, 2), {"kwarg0": 3, "kwarg1": 4}, None, None, None
        )
        redis_lru_obj.purge.assert_called_once_with(None)


class TestIncludeMe:
    @pytest.mark.parametrize(
        ("url", "cache_class"),
        [
            ("redis://", "RedisXMLRPCCache"),
            ("rediss://", "RedisXMLRPCCache"),
            ("null://", "NullXMLRPCCache"),
        ],
    )
    def test_configuration(self, url, cache_class, mocker):
        mocker.patch.object(cache, cache_class, autospec=True)

        config = types.SimpleNamespace(
            add_view_deriver=mocker.stub(name="add_view_deriver"),
            register_service_factory=mocker.stub(name="register_service_factory"),
            registry=types.SimpleNamespace(
                settings={"warehouse.xmlrpc.cache.url": url}
            ),
        )

        cache.includeme(config)

        config.add_view_deriver.assert_called_once_with(
            cache.cached_return_view, under="rendered_view", over="mapped_view"
        )

    def test_no_url_configuration(self):
        config = types.SimpleNamespace(registry=types.SimpleNamespace(settings={}))

        with pytest.raises(ConfigurationError):
            cache.includeme(config)

    def test_bad_url_configuration(self):
        config = types.SimpleNamespace(
            registry=types.SimpleNamespace(
                settings={"warehouse.xmlrpc.cache.url": "memcached://"}
            )
        )

        with pytest.raises(ConfigurationError):
            cache.includeme(config)

    def test_bad_expires_configuration(self):
        config = types.SimpleNamespace(
            registry=types.SimpleNamespace(
                settings={
                    "warehouse.xmlrpc.cache.url": "null://",
                    "warehouse.xmlrpc.cache.expires": "Never",
                }
            )
        )

        with pytest.raises(ConfigurationError):
            cache.includeme(config)

    def test_create_null_service(self, pyramid_request, mocker):
        pyramid_request.registry.settings.update(
            {"warehouse.xmlrpc.cache.url": "null://"}
        )
        delay = mocker.stub(name="delay")
        pyramid_request.task = mocker.Mock(return_value=mocker.Mock(delay=delay))

        service = NullXMLRPCCache.create_service(None, pyramid_request)
        service.purge_tags(["wu", "tang", "4", "evah"])

        assert isinstance(service, NullXMLRPCCache)
        assert service._purger is delay
        assert delay.call_args_list == [
            mocker.call("wu"),
            mocker.call("tang"),
            mocker.call("4"),
            mocker.call("evah"),
        ]

    def test_create_redis_service(self, pyramid_request, mocker):
        pyramid_request.registry.settings.update(
            {"warehouse.xmlrpc.cache.url": "redis://"}
        )
        delay = mocker.stub(name="delay")
        pyramid_request.task = mocker.Mock(return_value=mocker.Mock(delay=delay))

        service = RedisXMLRPCCache.create_service(None, pyramid_request)
        service.purge_tags(["wu", "tang", "4", "evah"])

        assert isinstance(service, RedisXMLRPCCache)
        assert service._purger is delay
        assert delay.call_args_list == [
            mocker.call("wu"),
            mocker.call("tang"),
            mocker.call("4"),
            mocker.call("evah"),
        ]


class TestRedisLru:
    def test_redis_lru(self, mockredis):
        redis_lru = RedisLru(mockredis)

        expected = func_test(0, 1, kwarg0=2, kwarg1=3)

        assert expected == redis_lru.fetch(
            func_test, [0, 1], {"kwarg0": 2, "kwarg1": 3}, None, None, None
        )
        assert expected == redis_lru.fetch(
            func_test, [0, 1], {"kwarg0": 2, "kwarg1": 3}, None, None, None
        )

    def test_redis_custom_metrics(self, metrics, mockredis, mocker):
        redis_lru = RedisLru(mockredis, metric_reporter=metrics)

        expected = func_test(0, 1, kwarg0=2, kwarg1=3)

        assert expected == redis_lru.fetch(
            func_test, [0, 1], {"kwarg0": 2, "kwarg1": 3}, None, None, None
        )
        assert expected == redis_lru.fetch(
            func_test, [0, 1], {"kwarg0": 2, "kwarg1": 3}, None, None, None
        )
        assert metrics.increment.call_args_list == [
            mocker.call("lru.cache.miss"),
            mocker.call("lru.cache.hit"),
        ]

    def test_redis_purge(self, metrics, mockredis, mocker):
        redis_lru = RedisLru(mockredis, metric_reporter=metrics)

        expected = func_test(0, 1, kwarg0=2, kwarg1=3)

        assert expected == redis_lru.fetch(
            func_test, [0, 1], {"kwarg0": 2, "kwarg1": 3}, None, "test", None
        )
        assert expected == redis_lru.fetch(
            func_test, [0, 1], {"kwarg0": 2, "kwarg1": 3}, None, "test", None
        )
        redis_lru.purge("test")
        assert expected == redis_lru.fetch(
            func_test, [0, 1], {"kwarg0": 2, "kwarg1": 3}, None, "test", None
        )
        assert expected == redis_lru.fetch(
            func_test, [0, 1], {"kwarg0": 2, "kwarg1": 3}, None, "test", None
        )
        assert metrics.increment.call_args_list == [
            mocker.call("lru.cache.miss"),
            mocker.call("lru.cache.hit"),
            mocker.call("lru.cache.purge"),
            mocker.call("lru.cache.miss"),
            mocker.call("lru.cache.hit"),
        ]

    def test_redis_down(self, metrics, mocker):
        down_redis = mocker.create_autospec(redis.StrictRedis, instance=True)
        down_redis.hget.side_effect = redis.exceptions.RedisError
        down_redis.pipeline.side_effect = redis.exceptions.RedisError
        down_redis.scan_iter.side_effect = redis.exceptions.RedisError
        redis_lru = RedisLru(down_redis, metric_reporter=metrics)

        expected = func_test(0, 1, kwarg0=2, kwarg1=3)

        assert expected == redis_lru.fetch(
            func_test, [0, 1], {"kwarg0": 2, "kwarg1": 3}, None, "test", None
        )
        assert expected == redis_lru.fetch(
            func_test, [0, 1], {"kwarg0": 2, "kwarg1": 3}, None, "test", None
        )
        with pytest.raises(CacheError):
            redis_lru.purge("test")

        assert metrics.increment.call_args_list == [
            mocker.call("lru.cache.error"),  # Failed get
            mocker.call("lru.cache.miss"),
            mocker.call("lru.cache.error"),  # Failed add
            mocker.call("lru.cache.error"),  # Failed get
            mocker.call("lru.cache.miss"),
            mocker.call("lru.cache.error"),  # Failed add
            mocker.call("lru.cache.error"),  # Failed purge
        ]


class TestDeriver:
    @pytest.mark.parametrize(
        ("service_available", "xmlrpc_cache"),
        [(True, True), (True, False), (False, True), (False, False)],
    )
    def test_deriver(self, service_available, xmlrpc_cache, mockredis, mocker):
        service = RedisXMLRPCCache(
            "redis://192.0.2.2:6379/0", mocker.stub(name="purger")
        )
        service.redis_conn = mockredis
        service.redis_lru.conn = mockredis
        if service_available:
            find_service = mocker.Mock(return_value=service)
        else:
            find_service = mocker.Mock(side_effect=LookupError)
        request = types.SimpleNamespace(
            find_service=find_service, rpc_method="rpc_method", rpc_args=(0, 1)
        )
        response = {}
        view = mocker.Mock(return_value=response, __name__="view")

        info = types.SimpleNamespace(
            options={"xmlrpc_cache": xmlrpc_cache}, exception_only=False
        )
        derived_view = cached_return_view(view, info)

        assert derived_view(mocker.sentinel.context, request) is response
        view.assert_called_once_with(mocker.sentinel.context, request)

    @pytest.mark.parametrize(
        ("service_available", "xmlrpc_cache"),
        [(True, True), (True, False), (False, True), (False, False)],
    )
    def test_custom_tag(self, service_available, xmlrpc_cache, mocker):
        service = NullXMLRPCCache("null://", mocker.stub(name="purger"))
        if service_available:
            find_service = mocker.Mock(return_value=service)
        else:
            find_service = mocker.Mock(side_effect=LookupError)
        request = types.SimpleNamespace(
            find_service=find_service,
            rpc_method="rpc_method",
            rpc_args=("warehouse", "1.0.0"),
        )
        response = {}
        view = mocker.Mock(return_value=response)

        info = types.SimpleNamespace(
            options={
                "xmlrpc_cache": xmlrpc_cache,
                "xmlrpc_cache_tag": "arg1/%s",
                "xmlrpc_cache_arg_index": 1,
            },
            exception_only=False,
        )
        derived_view = cached_return_view(view, info)

        assert derived_view(mocker.sentinel.context, request) is response
        view.assert_called_once_with(mocker.sentinel.context, request)

    @pytest.mark.parametrize(
        ("service_available", "xmlrpc_cache"),
        [(True, True), (True, False), (False, True), (False, False)],
    )
    def test_down_redis(self, service_available, xmlrpc_cache, mocker):
        service = NullXMLRPCCache("null://", mocker.stub(name="purger"))
        mocker.patch.object(service, "fetch", side_effect=CacheError)
        if service_available:
            find_service = mocker.Mock(return_value=service)
        else:
            find_service = mocker.Mock(side_effect=LookupError)
        request = types.SimpleNamespace(
            find_service=find_service, rpc_method="rpc_method", rpc_args=(0, 1)
        )
        response = mocker.sentinel.response
        view = mocker.Mock(return_value=response)

        info = types.SimpleNamespace(
            options={"xmlrpc_cache": xmlrpc_cache}, exception_only=False
        )
        derived_view = cached_return_view(view, info)  # miss
        derived_view = cached_return_view(view, info)  # hit

        assert derived_view(mocker.sentinel.context, request) is response
        view.assert_called_once_with(mocker.sentinel.context, request)


class TestPurgeTask:
    def test_purges_successfully(self, pyramid_request, mocker):
        service = NullXMLRPCCache("null://", mocker.stub(name="purger"))
        purge = mocker.spy(service, "purge")
        pyramid_request.find_service = mocker.Mock(return_value=service)

        services.purge_tag(mocker.sentinel.task, pyramid_request, "foo")

        pyramid_request.find_service.assert_called_once_with(IXMLRPCCache)
        purge.assert_called_once_with("foo")
        pyramid_request.log.info.assert_called_once_with("Purging %s", "foo")

    @pytest.mark.parametrize("exception_type", [CacheError])
    def test_purges_fails(self, pyramid_request, mocker, exception_type):
        exc = exception_type()

        service = NullXMLRPCCache("null://", mocker.stub(name="purger"))
        purge = mocker.patch.object(service, "purge", side_effect=exc)
        task = mocker.Mock()
        task.retry.side_effect = celery.exceptions.Retry
        pyramid_request.find_service = mocker.Mock(return_value=service)

        with pytest.raises(celery.exceptions.Retry):
            services.purge_tag(task, pyramid_request, "foo")

        pyramid_request.find_service.assert_called_once_with(IXMLRPCCache)
        purge.assert_called_once_with("foo")
        task.retry.assert_called_once_with(exc=exc)
        pyramid_request.log.info.assert_called_once_with("Purging %s", "foo")
        pyramid_request.log.error.assert_called_once_with(
            "Error purging %s: %s", "foo", str(exception_type())
        )

    def test_store_purge_keys(self, mocker):
        class Type1:
            pass

        class Type2:
            pass

        class Type3:
            pass

        class Type4:
            pass

        config = types.SimpleNamespace(
            registry={
                "cache_keys": {
                    Type1: lambda o: cache.CacheKeys(cache=[], purge=["type_1"]),
                    Type2: lambda o: cache.CacheKeys(cache=[], purge=["type_2", "foo"]),
                    Type3: lambda o: cache.CacheKeys(cache=[], purge=["type_3", "foo"]),
                }
            }
        )
        session = types.SimpleNamespace(
            info={}, new={Type1()}, dirty={Type2()}, deleted={Type3(), Type4()}
        )

        cache.store_purge_keys(config, session, mocker.sentinel.flush_context)

        assert session.info["warehouse.legacy.api.xmlrpc.cache.purges"] == {
            "type_1",
            "type_2",
            "type_3",
            "foo",
        }

    def test_execute_purge(self, app_config, mocker):
        service = NullXMLRPCCache("null://", mocker.stub(name="purger"))
        purge_tags = mocker.spy(service, "purge_tags")
        factory = mocker.Mock(return_value=service)
        app_config.register_service_factory(factory, IXMLRPCCache)
        app_config.commit()
        session = types.SimpleNamespace(
            info={
                "warehouse.legacy.api.xmlrpc.cache.purges": {
                    "type_1",
                    "type_2",
                    "foobar",
                }
            }
        )

        cache.execute_purge(app_config, session)

        factory.assert_called_once_with(None, app_config)
        purge_tags.assert_called_once_with({"type_1", "type_2", "foobar"})
        assert "warehouse.legacy.api.xmlrpc.cache.purges" not in session.info

    def test_execute_unsuccessful_purge(self, mocker):
        find_service_factory = mocker.Mock(side_effect=LookupError)
        config = types.SimpleNamespace(find_service_factory=find_service_factory)
        session = types.SimpleNamespace(
            info={
                "warehouse.legacy.api.xmlrpc.cache.purges": {
                    "type_1",
                    "type_2",
                    "foobar",
                }
            }
        )

        cache.execute_purge(config, session)

        find_service_factory.assert_called_once_with(IXMLRPCCache)
        assert "warehouse.legacy.api.xmlrpc.cache.purges" not in session.info
