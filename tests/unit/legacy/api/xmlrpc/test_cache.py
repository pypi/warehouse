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

import redis
import pretend
import pytest

from pyramid.exceptions import ConfigurationError

import warehouse.legacy.api.xmlrpc.cache
from warehouse.legacy.api.xmlrpc import cache
from warehouse.legacy.api.xmlrpc.cache import (
    cached_return_view,
    IXMLRPCCache,
    NullXMLRPCCache,
    RedisLru,
    RedisXMLRPCCache,
)
from warehouse.legacy.api.xmlrpc.cache.interfaces import CacheError


@pytest.fixture
def fakeredis():
    import fakeredis
    _fakeredis = fakeredis.FakeStrictRedis()
    yield _fakeredis
    _fakeredis.flushall()


def func_test(arg0, arg1, kwarg0=0, kwarg1=1):
    return [[arg0, arg1], {'kwarg0': kwarg0, 'kwarg1': kwarg1}]


class TestXMLRPCCache:

    def test_null_cache(self):
        service = NullXMLRPCCache()

        assert service.fetch(
            func_test, (1, 2), {'kwarg0': 3, 'kwarg1': 4}, None, None, None) \
            == [[1, 2], {'kwarg0': 3, 'kwarg1': 4}]

        assert service.purge(None) is None


class TestRedisXMLRPCCache:

    def test_redis_cache(self, monkeypatch):
        strict_redis_obj = pretend.stub()
        strict_redis_cls = pretend.stub(
            from_url=pretend.call_recorder(
                lambda url, db=None: strict_redis_obj
            ),
        )
        monkeypatch.setattr(redis, "StrictRedis", strict_redis_cls)

        redis_lru_obj = pretend.stub(
            fetch=pretend.call_recorder(
                lambda func, args, kwargs, key, tag, expires:
                    func(*args, **kwargs)
            ),
            purge=pretend.call_recorder(
                lambda tag: None
            )
        )
        redis_lru_cls = pretend.call_recorder(
            lambda redis_conn, **kwargs: redis_lru_obj
        )
        monkeypatch.setattr(
            warehouse.legacy.api.xmlrpc.cache,
            "RedisLru",
            redis_lru_cls,
        )

        service = RedisXMLRPCCache('redis://localhost:6379')

        assert strict_redis_cls.from_url.calls == [
            pretend.call("redis://localhost:6379", db=0)
        ]
        assert redis_lru_cls.calls == [
            pretend.call(
                strict_redis_obj,
                name='lru',
                expires=None,
                metric_reporter=None,
            )
        ]

        assert service.fetch(
            func_test, (1, 2), {'kwarg0': 3, 'kwarg1': 4}, None, None, None) \
            == [[1, 2], {'kwarg0': 3, 'kwarg1': 4}]

        assert service.purge(None) is None

        assert redis_lru_obj.fetch.calls == [
            pretend.call(
                func_test,
                (1, 2),
                {'kwarg0': 3, 'kwarg1': 4},
                None,
                None,
                None,
            )
        ]
        assert redis_lru_obj.purge.calls == [
            pretend.call(None)
        ]


class TestIncludeMe:

    @pytest.mark.parametrize(
        ('url', 'cache_class'),
        [
            ('redis://', 'RedisXMLRPCCache'),
            ('rediss://', 'RedisXMLRPCCache'),
            ('null://', 'NullXMLRPCCache'),
        ]
    )
    def test_configuration(self, url, cache_class, monkeypatch):
        client_obj = pretend.stub()
        client_cls = pretend.call_recorder(lambda *a, **kw: client_obj)
        monkeypatch.setattr(cache, cache_class, client_cls)

        registry = {}
        config = pretend.stub(
            add_view_deriver=pretend.call_recorder(
                lambda deriver, over=None, under=None: None
            ),
            register_service=pretend.call_recorder(
                lambda service, iface=None: None
            ),
            registry=pretend.stub(
                settings={"warehouse.xmlrpc.cache.url": url},
                __setitem__=registry.__setitem__,
            ),
        )

        cache.includeme(config)

        assert config.register_service.calls == [
            pretend.call(client_obj, iface=IXMLRPCCache)
        ]
        assert config.add_view_deriver.calls == [
            pretend.call(
                cache.cached_return_view,
                under='rendered_view', over='mapped_view'
            )
        ]

    def test_no_url_configuration(self, monkeypatch):
        registry = {}
        config = pretend.stub(
            registry=pretend.stub(
                settings={},
                __setitem__=registry.__setitem__,
            )
        )

        with pytest.raises(ConfigurationError):
            cache.includeme(config)

    def test_bad_url_configuration(self, monkeypatch):
        registry = {}
        config = pretend.stub(
            registry=pretend.stub(
                settings={
                    "warehouse.xmlrpc.cache.url": "memcached://",
                },
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
            ),
        )

        with pytest.raises(ConfigurationError):
            cache.includeme(config)


class TestRedisLru:

    def test_redis_lru(self, fakeredis):
        redis_lru = RedisLru(fakeredis)

        expected = func_test(0, 1, kwarg0=2, kwarg1=3)

        assert expected == redis_lru.fetch(
            func_test, [0, 1], {'kwarg0': 2, 'kwarg1': 3}, None, None, None
        )
        assert expected == redis_lru.fetch(
            func_test, [0, 1], {'kwarg0': 2, 'kwarg1': 3}, None, None, None
        )

    def test_redis_custom_metrics(self, fakeredis):
        metric_reporter = pretend.stub(
            increment=pretend.call_recorder(lambda *args: None)
        )
        redis_lru = RedisLru(fakeredis, metric_reporter=metric_reporter)

        expected = func_test(0, 1, kwarg0=2, kwarg1=3)

        assert expected == redis_lru.fetch(
            func_test, [0, 1], {'kwarg0': 2, 'kwarg1': 3}, None, None, None
        )
        assert expected == redis_lru.fetch(
            func_test, [0, 1], {'kwarg0': 2, 'kwarg1': 3}, None, None, None
        )
        assert metric_reporter.increment.calls == [
            pretend.call('lru.cache.miss'),
            pretend.call('lru.cache.hit'),
        ]

    def test_redis_purge(self, fakeredis):
        metric_reporter = pretend.stub(
            increment=pretend.call_recorder(lambda *args: None)
        )
        redis_lru = RedisLru(fakeredis, metric_reporter=metric_reporter)

        expected = func_test(0, 1, kwarg0=2, kwarg1=3)

        assert expected == redis_lru.fetch(
            func_test, [0, 1], {'kwarg0': 2, 'kwarg1': 3}, None, 'test', None
        )
        assert expected == redis_lru.fetch(
            func_test, [0, 1], {'kwarg0': 2, 'kwarg1': 3}, None, 'test', None
        )
        redis_lru.purge('test')
        assert expected == redis_lru.fetch(
            func_test, [0, 1], {'kwarg0': 2, 'kwarg1': 3}, None, 'test', None
        )
        assert expected == redis_lru.fetch(
            func_test, [0, 1], {'kwarg0': 2, 'kwarg1': 3}, None, 'test', None
        )
        assert metric_reporter.increment.calls == [
            pretend.call('lru.cache.miss'),
            pretend.call('lru.cache.hit'),
            pretend.call('lru.cache.purge'),
            pretend.call('lru.cache.miss'),
            pretend.call('lru.cache.hit'),
        ]

    def test_redis_down(self):
        metric_reporter = pretend.stub(
            increment=pretend.call_recorder(lambda *args: None)
        )
        down_redis = pretend.stub(
            hget=pretend.raiser(redis.exceptions.RedisError),
            pipeline=pretend.raiser(redis.exceptions.RedisError),
            scan_iter=pretend.raiser(redis.exceptions.RedisError),
        )
        redis_lru = RedisLru(down_redis, metric_reporter=metric_reporter)

        expected = func_test(0, 1, kwarg0=2, kwarg1=3)

        assert expected == redis_lru.fetch(
            func_test, [0, 1], {'kwarg0': 2, 'kwarg1': 3}, None, 'test', None
        )
        assert expected == redis_lru.fetch(
            func_test, [0, 1], {'kwarg0': 2, 'kwarg1': 3}, None, 'test', None
        )
        with pytest.raises(CacheError):
            redis_lru.purge('test')

        assert metric_reporter.increment.calls == [
            pretend.call('lru.cache.error'),  # Failed get
            pretend.call('lru.cache.miss'),
            pretend.call('lru.cache.error'),  # Failed add
            pretend.call('lru.cache.error'),  # Failed get
            pretend.call('lru.cache.miss'),
            pretend.call('lru.cache.error'),  # Failed add
            pretend.call('lru.cache.error'),  # Failed purge
        ]


class TestDeriver:

    @pytest.mark.parametrize(
        ("service_available", "xmlrpc_cache"),
        [
            (True, True),
            (True, False),
            (False, True),
            (False, False),
        ]
    )
    def test_deriver(self, service_available, xmlrpc_cache, fakeredis):
        context = pretend.stub()
        service = RedisXMLRPCCache('redis://127.0.0.2:6379/0')
        service.redis_conn = fakeredis
        service.redis_lru.conn = fakeredis
        if service_available:
            _find_service = pretend.call_recorder(
                lambda *args, **kwargs: service
            )
        else:
            _find_service = pretend.raiser(ValueError)
        request = pretend.stub(
            find_service=_find_service,
            rpc_method='rpc_method',
            rpc_args=(0, 1)
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
        [
            (True, True),
            (True, False),
            (False, True),
            (False, False),
        ]
    )
    def test_custom_tag(self, service_available, xmlrpc_cache):
        context = pretend.stub()
        service = pretend.stub(
            fetch=pretend.call_recorder(
                lambda func, args, kwargs, key, tag, expires:
                func(*args, **kwargs)
            )
        )
        if service_available:
            _find_service = pretend.call_recorder(
                lambda *args, **kwargs: service
            )
        else:
            _find_service = pretend.raiser(ValueError)
        request = pretend.stub(
            find_service=_find_service,
            rpc_method='rpc_method',
            rpc_args=(0, 1)
        )
        response = {}

        @pretend.call_recorder
        def view(context, request):
            return response

        info = pretend.stub(options={}, exception_only=False)
        info.options["xmlrpc_cache"] = xmlrpc_cache
        info.options["xmlrpc_cache_tag"] = 'arg1/%s'
        info.options["xmlrpc_cache_arg_index"] = 1
        derived_view = cached_return_view(view, info)

        assert derived_view(context, request) is response
        assert view.calls == [pretend.call(context, request)]

    @pytest.mark.parametrize(
        ("service_available", "xmlrpc_cache"),
        [
            (True, True),
            (True, False),
            (False, True),
            (False, False),
        ]
    )
    def test_down_redis(self, service_available, xmlrpc_cache):
        context = pretend.stub()
        service = pretend.stub(
            fetch=pretend.raiser(CacheError),
            purge=pretend.raiser(CacheError),
        )
        if service_available:
            _find_service = pretend.call_recorder(
                lambda *args, **kwargs: service
            )
        else:
            _find_service = pretend.raiser(ValueError)
        request = pretend.stub(
            find_service=_find_service,
            rpc_method='rpc_method',
            rpc_args=(0, 1)
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
