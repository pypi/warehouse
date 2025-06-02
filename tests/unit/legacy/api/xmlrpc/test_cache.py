# SPDX-License-Identifier: Apache-2.0

import celery
import pretend
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
    def test_null_cache(self):
        purger = pretend.call_recorder(lambda tags: None)
        service = NullXMLRPCCache("null://", purger)

        assert service.fetch(
            func_test, (1, 2), {"kwarg0": 3, "kwarg1": 4}, None, None, None
        ) == [[1, 2], {"kwarg0": 3, "kwarg1": 4}]

        assert service.purge(None) is None


class TestRedisXMLRPCCache:
    def test_redis_cache(self, monkeypatch):
        strict_redis_obj = pretend.stub()
        strict_redis_cls = pretend.stub(
            from_url=pretend.call_recorder(lambda url, db=None: strict_redis_obj)
        )
        monkeypatch.setattr(redis, "StrictRedis", strict_redis_cls)

        redis_lru_obj = pretend.stub(
            fetch=pretend.call_recorder(
                lambda func, args, kwargs, key, tag, expires: func(*args, **kwargs)
            ),
            purge=pretend.call_recorder(lambda tag: None),
        )
        redis_lru_cls = pretend.call_recorder(
            lambda redis_conn, **kwargs: redis_lru_obj
        )
        monkeypatch.setattr(
            warehouse.legacy.api.xmlrpc.cache, "RedisLru", redis_lru_cls
        )

        purger = pretend.call_recorder(lambda tags: None)

        service = RedisXMLRPCCache("redis://localhost:6379", purger)

        assert strict_redis_cls.from_url.calls == [
            pretend.call("redis://localhost:6379", db=0)
        ]
        assert redis_lru_cls.calls == [
            pretend.call(
                strict_redis_obj, name="lru", expires=None, metric_reporter=None
            )
        ]

        assert service.fetch(
            func_test, (1, 2), {"kwarg0": 3, "kwarg1": 4}, None, None, None
        ) == [[1, 2], {"kwarg0": 3, "kwarg1": 4}]

        assert service.purge(None) is None

        assert redis_lru_obj.fetch.calls == [
            pretend.call(
                func_test, (1, 2), {"kwarg0": 3, "kwarg1": 4}, None, None, None
            )
        ]
        assert redis_lru_obj.purge.calls == [pretend.call(None)]


class TestIncludeMe:
    @pytest.mark.parametrize(
        ("url", "cache_class"),
        [
            ("redis://", "RedisXMLRPCCache"),
            ("rediss://", "RedisXMLRPCCache"),
            ("null://", "NullXMLRPCCache"),
        ],
    )
    def test_configuration(self, url, cache_class, monkeypatch):
        client_obj = pretend.stub()
        client_cls = pretend.stub(
            create_service=pretend.call_recorder(lambda *a, **kw: client_obj)
        )
        monkeypatch.setattr(cache, cache_class, client_cls)

        registry = {}
        config = pretend.stub(
            add_view_deriver=pretend.call_recorder(
                lambda deriver, over=None, under=None: None
            ),
            register_service_factory=pretend.call_recorder(
                lambda service, iface=None: None
            ),
            registry=pretend.stub(
                settings={"warehouse.xmlrpc.cache.url": url},
                __setitem__=registry.__setitem__,
            ),
        )

        cache.includeme(config)

        assert config.add_view_deriver.calls == [
            pretend.call(
                cache.cached_return_view, under="rendered_view", over="mapped_view"
            )
        ]

    def test_no_url_configuration(self, monkeypatch):
        registry = {}
        config = pretend.stub(
            registry=pretend.stub(settings={}, __setitem__=registry.__setitem__)
        )

        with pytest.raises(ConfigurationError):
            cache.includeme(config)

    def test_bad_url_configuration(self, monkeypatch):
        registry = {}
        config = pretend.stub(
            registry=pretend.stub(
                settings={"warehouse.xmlrpc.cache.url": "memcached://"},
                __setitem__=registry.__setitem__,
            )
        )

        with pytest.raises(ConfigurationError):
            cache.includeme(config)

    def test_bad_expires_configuration(self, monkeypatch):
        client_obj = pretend.stub()
        client_cls = pretend.call_recorder(lambda *a, **kw: client_obj)
        monkeypatch.setattr(cache, "NullXMLRPCCache", client_cls)

        registry = {}
        config = pretend.stub(
            registry=pretend.stub(
                settings={
                    "warehouse.xmlrpc.cache.url": "null://",
                    "warehouse.xmlrpc.cache.expires": "Never",
                },
                __setitem__=registry.__setitem__,
            )
        )

        with pytest.raises(ConfigurationError):
            cache.includeme(config)

    def test_create_null_service(self):
        purge_tags = pretend.stub(delay=pretend.call_recorder(lambda tag: None))
        request = pretend.stub(
            registry=pretend.stub(settings={"warehouse.xmlrpc.cache.url": "null://"}),
            task=lambda f: purge_tags,
        )
        service = NullXMLRPCCache.create_service(None, request)
        service.purge_tags(["wu", "tang", "4", "evah"])
        assert isinstance(service, NullXMLRPCCache)
        assert service._purger is purge_tags.delay
        assert purge_tags.delay.calls == [
            pretend.call("wu"),
            pretend.call("tang"),
            pretend.call("4"),
            pretend.call("evah"),
        ]

    def test_create_redis_service(self):
        purge_tags = pretend.stub(delay=pretend.call_recorder(lambda tag: None))
        request = pretend.stub(
            registry=pretend.stub(settings={"warehouse.xmlrpc.cache.url": "redis://"}),
            task=lambda f: purge_tags,
        )
        service = RedisXMLRPCCache.create_service(None, request)
        service.purge_tags(["wu", "tang", "4", "evah"])
        assert isinstance(service, RedisXMLRPCCache)
        assert service._purger is purge_tags.delay
        assert purge_tags.delay.calls == [
            pretend.call("wu"),
            pretend.call("tang"),
            pretend.call("4"),
            pretend.call("evah"),
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

    def test_redis_custom_metrics(self, metrics, mockredis):
        redis_lru = RedisLru(mockredis, metric_reporter=metrics)

        expected = func_test(0, 1, kwarg0=2, kwarg1=3)

        assert expected == redis_lru.fetch(
            func_test, [0, 1], {"kwarg0": 2, "kwarg1": 3}, None, None, None
        )
        assert expected == redis_lru.fetch(
            func_test, [0, 1], {"kwarg0": 2, "kwarg1": 3}, None, None, None
        )
        assert metrics.increment.calls == [
            pretend.call("lru.cache.miss"),
            pretend.call("lru.cache.hit"),
        ]

    def test_redis_purge(self, metrics, mockredis):
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
        assert metrics.increment.calls == [
            pretend.call("lru.cache.miss"),
            pretend.call("lru.cache.hit"),
            pretend.call("lru.cache.purge"),
            pretend.call("lru.cache.miss"),
            pretend.call("lru.cache.hit"),
        ]

    def test_redis_down(self, metrics):
        down_redis = pretend.stub(
            hget=pretend.raiser(redis.exceptions.RedisError),
            pipeline=pretend.raiser(redis.exceptions.RedisError),
            scan_iter=pretend.raiser(redis.exceptions.RedisError),
        )
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

        assert metrics.increment.calls == [
            pretend.call("lru.cache.error"),  # Failed get
            pretend.call("lru.cache.miss"),
            pretend.call("lru.cache.error"),  # Failed add
            pretend.call("lru.cache.error"),  # Failed get
            pretend.call("lru.cache.miss"),
            pretend.call("lru.cache.error"),  # Failed add
            pretend.call("lru.cache.error"),  # Failed purge
        ]


class TestDeriver:
    @pytest.mark.parametrize(
        ("service_available", "xmlrpc_cache"),
        [(True, True), (True, False), (False, True), (False, False)],
    )
    def test_deriver(self, service_available, xmlrpc_cache, mockredis):
        context = pretend.stub()
        purger = pretend.call_recorder(lambda tags: None)
        service = RedisXMLRPCCache("redis://127.0.0.2:6379/0", purger)
        service.redis_conn = mockredis
        service.redis_lru.conn = mockredis
        if service_available:
            _find_service = pretend.call_recorder(lambda *args, **kwargs: service)
        else:
            _find_service = pretend.raiser(LookupError)
        request = pretend.stub(
            find_service=_find_service, rpc_method="rpc_method", rpc_args=(0, 1)
        )
        response = {}

        @pretend.call_recorder
        def view(context, request):
            return response

        info = pretend.stub(options={}, exception_only=False)
        info.options["xmlrpc_cache"] = xmlrpc_cache
        derived_view = cached_return_view(view, info)

        assert derived_view(context, request) is response
        assert view.calls == [pretend.call(context, request)]

    @pytest.mark.parametrize(
        ("service_available", "xmlrpc_cache"),
        [(True, True), (True, False), (False, True), (False, False)],
    )
    def test_custom_tag(self, service_available, xmlrpc_cache):
        context = pretend.stub()
        service = pretend.stub(
            fetch=pretend.call_recorder(
                lambda func, args, kwargs, key, tag, expires: func(*args, **kwargs)
            )
        )
        if service_available:
            _find_service = pretend.call_recorder(lambda *args, **kwargs: service)
        else:
            _find_service = pretend.raiser(LookupError)
        request = pretend.stub(
            find_service=_find_service,
            rpc_method="rpc_method",
            rpc_args=("warehouse", "1.0.0"),
        )
        response = {}

        @pretend.call_recorder
        def view(context, request):
            return response

        info = pretend.stub(options={}, exception_only=False)
        info.options["xmlrpc_cache"] = xmlrpc_cache
        info.options["xmlrpc_cache_tag"] = "arg1/%s"
        info.options["xmlrpc_cache_arg_index"] = 1
        derived_view = cached_return_view(view, info)

        assert derived_view(context, request) is response
        assert view.calls == [pretend.call(context, request)]

    @pytest.mark.parametrize(
        ("service_available", "xmlrpc_cache"),
        [(True, True), (True, False), (False, True), (False, False)],
    )
    def test_down_redis(self, service_available, xmlrpc_cache):
        context = pretend.stub()
        service = pretend.stub(
            fetch=pretend.raiser(CacheError), purge=pretend.raiser(CacheError)
        )
        if service_available:
            _find_service = pretend.call_recorder(lambda *args, **kwargs: service)
        else:
            _find_service = pretend.raiser(LookupError)
        request = pretend.stub(
            find_service=_find_service, rpc_method="rpc_method", rpc_args=(0, 1)
        )
        response = pretend.stub()

        @pretend.call_recorder
        def view(context, request):
            return response

        info = pretend.stub(options={}, exception_only=False)
        info.options["xmlrpc_cache"] = xmlrpc_cache
        derived_view = cached_return_view(view, info)  # miss
        derived_view = cached_return_view(view, info)  # hit

        assert derived_view(context, request) is response
        assert view.calls == [pretend.call(context, request)]


class TestPurgeTask:
    def test_purges_successfully(self, monkeypatch):
        task = pretend.stub()
        service = pretend.stub(purge=pretend.call_recorder(lambda k: None))
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda iface: service),
            log=pretend.stub(info=pretend.call_recorder(lambda *args, **kwargs: None)),
        )

        services.purge_tag(task, request, "foo")

        assert request.find_service.calls == [pretend.call(IXMLRPCCache)]
        assert service.purge.calls == [pretend.call("foo")]
        assert request.log.info.calls == [pretend.call("Purging %s", "foo")]

    @pytest.mark.parametrize("exception_type", [CacheError])
    def test_purges_fails(self, monkeypatch, exception_type):
        exc = exception_type()

        class Cache:
            @staticmethod
            @pretend.call_recorder
            def purge(key):
                raise exc

        class Task:
            @staticmethod
            @pretend.call_recorder
            def retry(exc):
                raise celery.exceptions.Retry

        task = Task()
        service = Cache()
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda iface: service),
            log=pretend.stub(
                info=pretend.call_recorder(lambda *args, **kwargs: None),
                error=pretend.call_recorder(lambda *args, **kwargs: None),
            ),
        )

        with pytest.raises(celery.exceptions.Retry):
            services.purge_tag(task, request, "foo")

        assert request.find_service.calls == [pretend.call(IXMLRPCCache)]
        assert service.purge.calls == [pretend.call("foo")]
        assert task.retry.calls == [pretend.call(exc=exc)]
        assert request.log.info.calls == [pretend.call("Purging %s", "foo")]
        assert request.log.error.calls == [
            pretend.call("Error purging %s: %s", "foo", str(exception_type()))
        ]

    def test_store_purge_keys(self):
        class Type1:
            pass

        class Type2:
            pass

        class Type3:
            pass

        class Type4:
            pass

        config = pretend.stub(
            registry={
                "cache_keys": {
                    Type1: lambda o: cache.CacheKeys(cache=[], purge=["type_1"]),
                    Type2: lambda o: cache.CacheKeys(cache=[], purge=["type_2", "foo"]),
                    Type3: lambda o: cache.CacheKeys(cache=[], purge=["type_3", "foo"]),
                }
            }
        )
        session = pretend.stub(
            info={}, new={Type1()}, dirty={Type2()}, deleted={Type3(), Type4()}
        )

        cache.store_purge_keys(config, session, pretend.stub())

        assert session.info["warehouse.legacy.api.xmlrpc.cache.purges"] == {
            "type_1",
            "type_2",
            "type_3",
            "foo",
        }

    def test_execute_purge(self, app_config):
        service = pretend.stub(purge_tags=pretend.call_recorder(lambda purges: None))
        factory = pretend.call_recorder(lambda ctx, config: service)
        app_config.register_service_factory(factory, IXMLRPCCache)
        app_config.commit()
        session = pretend.stub(
            info={
                "warehouse.legacy.api.xmlrpc.cache.purges": {
                    "type_1",
                    "type_2",
                    "foobar",
                }
            }
        )

        cache.execute_purge(app_config, session)

        assert factory.calls == [pretend.call(None, app_config)]
        assert service.purge_tags.calls == [
            pretend.call({"type_1", "type_2", "foobar"})
        ]
        assert "warehouse.legacy.api.xmlrpc.cache.purges" not in session.info

    def test_execute_unsuccessful_purge(self):
        @pretend.call_recorder
        def find_service_factory(interface):
            raise LookupError

        config = pretend.stub(find_service_factory=find_service_factory)
        session = pretend.stub(
            info={
                "warehouse.legacy.api.xmlrpc.cache.purges": {
                    "type_1",
                    "type_2",
                    "foobar",
                }
            }
        )

        cache.execute_purge(config, session)

        assert find_service_factory.calls == [pretend.call(IXMLRPCCache)]
        assert "warehouse.legacy.api.xmlrpc.cache.purges" not in session.info
