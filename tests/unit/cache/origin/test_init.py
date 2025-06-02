# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from warehouse.cache import origin
from warehouse.cache.origin.derivers import html_cache_deriver
from warehouse.cache.origin.interfaces import IOriginCache


def test_store_purge_keys():
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
                Type1: lambda o: origin.CacheKeys(cache=[], purge=["type_1"]),
                Type2: lambda o: origin.CacheKeys(cache=[], purge=["type_2", "foo"]),
                Type3: lambda o: origin.CacheKeys(cache=[], purge=["type_3", "foo"]),
            }
        }
    )
    session = pretend.stub(
        info={}, new={Type1()}, dirty={Type2()}, deleted={Type3(), Type4()}
    )

    origin.store_purge_keys(config, session, pretend.stub())

    assert session.info["warehouse.cache.origin.purges"] == {
        "type_1",
        "type_2",
        "type_3",
        "foo",
    }


def test_execute_purge_success(app_config, monkeypatch):
    cacher = pretend.stub(purge=pretend.call_recorder(lambda purges: None))
    factory = pretend.call_recorder(lambda ctx, config: cacher)
    monkeypatch.setattr(app_config, "find_service_factory", lambda *a, **kw: factory)
    session = pretend.stub(
        info={"warehouse.cache.origin.purges": {"type_1", "type_2", "foobar"}}
    )

    origin.execute_purge(app_config, session)

    assert factory.calls == [pretend.call(None, app_config)]
    assert cacher.purge.calls == [pretend.call({"type_1", "type_2", "foobar"})]
    assert "warehouse.cache.origin.purges" not in session.info


def test_execute_purge_no_backend():
    @pretend.call_recorder
    def find_service_factory(interface):
        raise LookupError

    config = pretend.stub(find_service_factory=find_service_factory)
    session = pretend.stub(
        info={"warehouse.cache.origin.purges": {"type_1", "type_2", "foobar"}}
    )

    origin.execute_purge(config, session)

    assert find_service_factory.calls == [pretend.call(origin.IOriginCache)]
    assert "warehouse.cache.origin.purges" not in session.info


class TestOriginCache:
    def test_no_cache_key(self):
        response = pretend.stub()

        @origin.origin_cache(1)
        def view(context, request):
            return response

        def raiser(iface):
            raise LookupError

        context = pretend.stub()
        request = pretend.stub(registry={"cache_keys": {}}, find_service=raiser)

        assert view(context, request) is response

    def test_no_origin_cache(self):
        class Fake:
            pass

        response = pretend.stub()

        @origin.origin_cache(1)
        def view(context, request):
            return response

        @pretend.call_recorder
        def raiser(iface):
            raise LookupError

        context = Fake()
        request = pretend.stub(
            registry={
                "cache_keys": {Fake: lambda X: origin.CacheKeys(cache=[], purge=[])}
            },
            find_service=raiser,
        )

        assert view(context, request) is response
        assert raiser.calls == [pretend.call(IOriginCache)]

    @pytest.mark.parametrize(("seconds", "keys"), [(745, None), (823, ["nope", "yup"])])
    def test_response_hook(self, seconds, keys):
        class Fake:
            pass

        class Cache:
            @staticmethod
            @pretend.call_recorder
            def cache(
                keys, request, response, seconds, stale_while_revalidate, stale_if_error
            ):
                pass

        response = pretend.stub()

        deco = origin.origin_cache(seconds, keys=keys)

        @deco
        def view(context, request):
            return response

        key_maker = pretend.call_recorder(
            lambda obj: origin.CacheKeys(cache=["one", "two"], purge=[])
        )
        cacher = Cache()
        context = Fake()
        callbacks = []
        request = pretend.stub(
            registry={"cache_keys": {Fake: key_maker}},
            find_service=lambda iface: cacher,
            add_response_callback=callbacks.append,
        )

        assert view(context, request) is response
        assert key_maker.calls == [pretend.call(context)]
        assert len(callbacks) == 1

        callbacks[0](request, response)

        assert cacher.cache.calls == [
            pretend.call(
                ["one", "two"] + ([] if keys is None else keys),
                request,
                response,
                seconds=seconds,
                stale_while_revalidate=None,
                stale_if_error=None,
            )
        ]


class TestKeyMaker:
    def test_both_cache_and_purge(self):
        key_maker = origin.key_maker_factory(
            cache_keys=["foo", "foo/{obj.attr}"],
            purge_keys=[
                origin.key_factory("bar"),
                origin.key_factory("bar/{obj.attr}"),
            ],
        )
        cache_keys = key_maker(pretend.stub(attr="bar"))

        assert isinstance(cache_keys, origin.CacheKeys)
        assert cache_keys.cache == ["foo", "foo/bar"]
        assert list(cache_keys.purge) == ["bar", "bar/bar"]

    def test_only_cache(self):
        key_maker = origin.key_maker_factory(
            cache_keys=["foo", "foo/{obj.attr}"], purge_keys=None
        )
        cache_keys = key_maker(pretend.stub(attr="bar"))

        assert isinstance(cache_keys, origin.CacheKeys)
        assert cache_keys.cache == ["foo", "foo/bar"]
        assert list(cache_keys.purge) == []

    def test_only_purge(self):
        key_maker = origin.key_maker_factory(
            cache_keys=None,
            purge_keys=[
                origin.key_factory("bar"),
                origin.key_factory("bar/{obj.attr}"),
            ],
        )
        cache_keys = key_maker(pretend.stub(attr="bar"))

        assert isinstance(cache_keys, origin.CacheKeys)
        assert cache_keys.cache == []
        assert list(cache_keys.purge) == ["bar", "bar/bar"]

    def test_iterate_on(self):
        key_maker = origin.key_maker_factory(
            cache_keys=["foo"],  # Intentionally does not support `iterate_on`
            purge_keys=[
                origin.key_factory("bar"),
                origin.key_factory("bar/{itr}", iterate_on="iterate_me"),
            ],
        )
        cache_keys = key_maker(pretend.stub(iterate_me=["biz", "baz"]))

        assert isinstance(cache_keys, origin.CacheKeys)
        assert cache_keys.cache == ["foo"]
        assert list(cache_keys.purge) == ["bar", "bar/biz", "bar/baz"]

    def test_if_attr_exists_exists(self):
        key_maker = origin.key_maker_factory(
            cache_keys=["foo"],
            purge_keys=[
                origin.key_factory("bar"),
                origin.key_factory("bar/{attr}", if_attr_exists="foo"),
            ],
        )
        cache_keys = key_maker(pretend.stub(foo="bar"))

        assert isinstance(cache_keys, origin.CacheKeys)
        assert cache_keys.cache == ["foo"]
        assert list(cache_keys.purge) == ["bar", "bar/bar"]

    def test_if_attr_exists_nested(self):
        key_maker = origin.key_maker_factory(
            cache_keys=["foo"],
            purge_keys=[
                origin.key_factory("bar"),
                origin.key_factory("bar/{attr}", if_attr_exists="foo.bar"),
            ],
        )
        cache_keys = key_maker(pretend.stub(foo=pretend.stub(bar="bar")))

        assert isinstance(cache_keys, origin.CacheKeys)
        assert cache_keys.cache == ["foo"]
        assert list(cache_keys.purge) == ["bar", "bar/bar"]

    def test_if_attr_exists_does_not_exist(self):
        key_maker = origin.key_maker_factory(
            cache_keys=["foo"],
            purge_keys=[
                origin.key_factory("bar"),
                origin.key_factory("bar/{attr}", if_attr_exists="foo"),
            ],
        )
        cache_keys = key_maker(pretend.stub())

        assert isinstance(cache_keys, origin.CacheKeys)
        assert cache_keys.cache == ["foo"]
        assert list(cache_keys.purge) == ["bar"]

    def test_if_attr_exists_nested_does_not_exist(self):
        key_maker = origin.key_maker_factory(
            cache_keys=["foo"],
            purge_keys=[
                origin.key_factory("bar"),
                origin.key_factory("bar/{attr}", if_attr_exists="foo.bar"),
            ],
        )
        cache_keys = key_maker(pretend.stub())

        assert isinstance(cache_keys, origin.CacheKeys)
        assert cache_keys.cache == ["foo"]
        assert list(cache_keys.purge) == ["bar"]


def test_register_origin_keys(monkeypatch):
    class Fake1:
        pass

    class Fake2:
        pass

    key_maker = pretend.stub()
    key_maker_factory = pretend.call_recorder(lambda **kw: key_maker)
    monkeypatch.setattr(origin, "key_maker_factory", key_maker_factory)

    config = pretend.stub(registry={})

    origin.register_origin_cache_keys(
        config, Fake1, cache_keys=["one", "two/{obj.attr}"]
    )
    origin.register_origin_cache_keys(
        config, Fake2, cache_keys=["three"], purge_keys=["lol"]
    )

    assert key_maker_factory.calls == [
        pretend.call(cache_keys=["one", "two/{obj.attr}"], purge_keys=None),
        pretend.call(cache_keys=["three"], purge_keys=["lol"]),
    ]
    assert config.registry == {"cache_keys": {Fake1: key_maker, Fake2: key_maker}}


def test_includeme_no_origin_cache():
    config = pretend.stub(
        add_directive=pretend.call_recorder(lambda name, func: None),
        registry=pretend.stub(settings={}),
    )

    origin.includeme(config)

    assert config.add_directive.calls == [
        pretend.call("register_origin_cache_keys", origin.register_origin_cache_keys)
    ]


def test_includeme_with_origin_cache():
    cache_class = pretend.stub(create_service=pretend.stub())
    config = pretend.stub(
        add_directive=pretend.call_recorder(lambda name, func: None),
        add_view_deriver=pretend.call_recorder(lambda deriver: None),
        registry=pretend.stub(
            settings={
                "origin_cache.backend": "warehouse.cache.origin.fastly.FastlyCache"
            }
        ),
        maybe_dotted=pretend.call_recorder(lambda n: cache_class),
        register_service_factory=pretend.call_recorder(lambda f, iface: None),
    )

    origin.includeme(config)

    assert config.add_directive.calls == [
        pretend.call("register_origin_cache_keys", origin.register_origin_cache_keys)
    ]
    assert config.add_view_deriver.calls == [pretend.call(html_cache_deriver)]
    assert config.maybe_dotted.calls == [
        pretend.call("warehouse.cache.origin.fastly.FastlyCache")
    ]
    assert config.register_service_factory.calls == [
        pretend.call(cache_class.create_service, IOriginCache)
    ]
