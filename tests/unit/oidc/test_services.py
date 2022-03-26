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

import fakeredis
import pretend

from jwt import PyJWK
from zope.interface.verify import verifyClass

from warehouse.oidc import interfaces, services


def test_oidc_provider_service_factory():
    factory = services.OIDCProviderServiceFactory(
        provider="example", issuer_url="https://example.com"
    )

    assert factory.provider == "example"
    assert factory.issuer_url == "https://example.com"
    assert verifyClass(interfaces.IOIDCProviderService, factory.service_class)

    metrics = pretend.stub()
    request = pretend.stub(
        registry=pretend.stub(
            settings={"oidc.jwk_cache_url": "rediss://another.example.com"}
        ),
        find_service=lambda *a, **kw: metrics,
    )
    service = factory(pretend.stub(), request)

    assert isinstance(service, factory.service_class)
    assert service.provider == factory.provider
    assert service.issuer_url == factory.issuer_url
    assert service.cache_url == "rediss://another.example.com"
    assert service.metrics == metrics

    assert factory != object()
    assert factory != services.OIDCProviderServiceFactory(
        provider="another", issuer_url="https://foo.example.com"
    )


class TestOIDCProviderService:
    def test_verify(self):
        service = services.OIDCProviderService(
            provider=pretend.stub(),
            issuer_url=pretend.stub(),
            cache_url=pretend.stub(),
            metrics=pretend.stub(),
        )
        assert service.verify(pretend.stub()) == NotImplemented

    def test_get_keyset_not_cached(self, monkeypatch):
        service = services.OIDCProviderService(
            provider="example",
            issuer_url=pretend.stub(),
            cache_url="rediss://fake.example.com",
            metrics=pretend.stub(),
        )

        monkeypatch.setattr(services.redis, "StrictRedis", fakeredis.FakeStrictRedis)
        keys, timeout = service._get_keyset()

        assert not keys
        assert timeout is False

    def test_get_keyset_cached(self, monkeypatch):
        service = services.OIDCProviderService(
            provider="example",
            issuer_url=pretend.stub(),
            cache_url="rediss://fake.example.com",
            metrics=pretend.stub(),
        )

        # Create a fake server to provide persistent state through each
        # StrictRedis.from_url context manager.
        server = fakeredis.FakeServer()
        from_url = functools.partial(fakeredis.FakeStrictRedis.from_url, server=server)
        monkeypatch.setattr(services.redis.StrictRedis, "from_url", from_url)

        keyset = {"fake-key-id": {"foo": "bar"}}
        service._store_keyset(keyset)
        keys, timeout = service._get_keyset()

        assert keys == keyset
        assert timeout is True

    def test_refresh_keyset_timeout(self, monkeypatch):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
            cache_url="rediss://fake.example.com",
            metrics=metrics,
        )

        # Create a fake server to provide persistent state through each
        # StrictRedis.from_url context manager.
        server = fakeredis.FakeServer()
        from_url = functools.partial(fakeredis.FakeStrictRedis.from_url, server=server)
        monkeypatch.setattr(services.redis.StrictRedis, "from_url", from_url)

        keyset = {"fake-key-id": {"foo": "bar"}}
        service._store_keyset(keyset)

        keys = service._refresh_keyset()
        assert keys == keyset
        assert metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.refresh_keyset.timeout", tags=["provider:example"]
            )
        ]

    def test_refresh_keyset_oidc_config_fails(self, monkeypatch):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
            cache_url="rediss://fake.example.com",
            metrics=metrics,
        )

        monkeypatch.setattr(services.redis, "StrictRedis", fakeredis.FakeStrictRedis)

        requests = pretend.stub(
            get=pretend.call_recorder(lambda url: pretend.stub(ok=False))
        )
        sentry_sdk = pretend.stub(
            capture_message=pretend.call_recorder(lambda msg: pretend.stub())
        )
        monkeypatch.setattr(services, "requests", requests)
        monkeypatch.setattr(services, "sentry_sdk", sentry_sdk)

        keys = service._refresh_keyset()

        assert keys == {}
        assert metrics.increment.calls == []
        assert requests.get.calls == [
            pretend.call("https://example.com/.well-known/openid-configuration")
        ]
        assert sentry_sdk.capture_message.calls == [
            pretend.call(
                "OIDC provider example failed to return configuration: "
                "https://example.com/.well-known/openid-configuration"
            )
        ]

    def test_refresh_keyset_oidc_config_no_jwks_uri(self, monkeypatch):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
            cache_url="rediss://fake.example.com",
            metrics=metrics,
        )

        monkeypatch.setattr(services.redis, "StrictRedis", fakeredis.FakeStrictRedis)

        requests = pretend.stub(
            get=pretend.call_recorder(
                lambda url: pretend.stub(ok=True, json=lambda: {})
            )
        )
        sentry_sdk = pretend.stub(
            capture_message=pretend.call_recorder(lambda msg: pretend.stub())
        )
        monkeypatch.setattr(services, "requests", requests)
        monkeypatch.setattr(services, "sentry_sdk", sentry_sdk)

        keys = service._refresh_keyset()

        assert keys == {}
        assert metrics.increment.calls == []
        assert requests.get.calls == [
            pretend.call("https://example.com/.well-known/openid-configuration")
        ]
        assert sentry_sdk.capture_message.calls == [
            pretend.call(
                "OIDC provider example is returning malformed configuration "
                "(no jwks_uri)"
            )
        ]

    def test_refresh_keyset_oidc_config_no_jwks_json(self, monkeypatch):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
            cache_url="rediss://fake.example.com",
            metrics=metrics,
        )

        monkeypatch.setattr(services.redis, "StrictRedis", fakeredis.FakeStrictRedis)

        openid_resp = pretend.stub(
            ok=True,
            json=lambda: {
                "jwks_uri": "https://example.com/.well-known/jwks.json",
            },
        )
        jwks_resp = pretend.stub(ok=False)

        def get(url):
            if url == "https://example.com/.well-known/jwks.json":
                return jwks_resp
            else:
                return openid_resp

        requests = pretend.stub(get=pretend.call_recorder(get))
        sentry_sdk = pretend.stub(
            capture_message=pretend.call_recorder(lambda msg: pretend.stub())
        )
        monkeypatch.setattr(services, "requests", requests)
        monkeypatch.setattr(services, "sentry_sdk", sentry_sdk)

        keys = service._refresh_keyset()

        assert keys == {}
        assert metrics.increment.calls == []
        assert requests.get.calls == [
            pretend.call("https://example.com/.well-known/openid-configuration"),
            pretend.call("https://example.com/.well-known/jwks.json"),
        ]
        assert sentry_sdk.capture_message.calls == [
            pretend.call(
                "OIDC provider example failed to return JWKS JSON: "
                "https://example.com/.well-known/jwks.json"
            )
        ]

    def test_refresh_keyset_oidc_config_no_jwks_keys(self, monkeypatch):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
            cache_url="rediss://fake.example.com",
            metrics=metrics,
        )

        monkeypatch.setattr(services.redis, "StrictRedis", fakeredis.FakeStrictRedis)

        openid_resp = pretend.stub(
            ok=True,
            json=lambda: {
                "jwks_uri": "https://example.com/.well-known/jwks.json",
            },
        )
        jwks_resp = pretend.stub(ok=True, json=lambda: {})

        def get(url):
            if url == "https://example.com/.well-known/jwks.json":
                return jwks_resp
            else:
                return openid_resp

        requests = pretend.stub(get=pretend.call_recorder(get))
        sentry_sdk = pretend.stub(
            capture_message=pretend.call_recorder(lambda msg: pretend.stub())
        )
        monkeypatch.setattr(services, "requests", requests)
        monkeypatch.setattr(services, "sentry_sdk", sentry_sdk)

        keys = service._refresh_keyset()

        assert keys == {}
        assert metrics.increment.calls == []
        assert requests.get.calls == [
            pretend.call("https://example.com/.well-known/openid-configuration"),
            pretend.call("https://example.com/.well-known/jwks.json"),
        ]
        assert sentry_sdk.capture_message.calls == [
            pretend.call("OIDC provider example returned JWKS JSON but no keys")
        ]

    def test_refresh_keyset_successful(self, monkeypatch):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
            cache_url="rediss://fake.example.com",
            metrics=metrics,
        )

        # Create a fake server to provide persistent state through each
        # StrictRedis.from_url context manager.
        server = fakeredis.FakeServer()
        from_url = functools.partial(fakeredis.FakeStrictRedis.from_url, server=server)
        monkeypatch.setattr(services.redis.StrictRedis, "from_url", from_url)

        openid_resp = pretend.stub(
            ok=True,
            json=lambda: {
                "jwks_uri": "https://example.com/.well-known/jwks.json",
            },
        )
        jwks_resp = pretend.stub(
            ok=True, json=lambda: {"keys": [{"kid": "fake-key-id", "foo": "bar"}]}
        )

        def get(url):
            if url == "https://example.com/.well-known/jwks.json":
                return jwks_resp
            else:
                return openid_resp

        requests = pretend.stub(get=pretend.call_recorder(get))
        sentry_sdk = pretend.stub(
            capture_message=pretend.call_recorder(lambda msg: pretend.stub())
        )
        monkeypatch.setattr(services, "requests", requests)
        monkeypatch.setattr(services, "sentry_sdk", sentry_sdk)

        keys = service._refresh_keyset()

        assert keys == {"fake-key-id": {"kid": "fake-key-id", "foo": "bar"}}
        assert metrics.increment.calls == []
        assert requests.get.calls == [
            pretend.call("https://example.com/.well-known/openid-configuration"),
            pretend.call("https://example.com/.well-known/jwks.json"),
        ]
        assert sentry_sdk.capture_message.calls == []

        # Ensure that we also cached the updated keyset as part of refreshing.
        keys, timeout = service._get_keyset()
        assert keys == {"fake-key-id": {"kid": "fake-key-id", "foo": "bar"}}
        assert timeout is True

    def test_get_key_cached(self, monkeypatch):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
            cache_url="rediss://fake.example.com",
            metrics=metrics,
        )

        keyset = {
            "fake-key-id": {
                "kid": "fake-key-id",
                "n": "ZHVtbXkK",
                "kty": "RSA",
                "alg": "RS256",
                "e": "AQAB",
                "use": "sig",
                "x5c": ["dummy"],
                "x5t": "dummy",
            }
        }
        monkeypatch.setattr(service, "_get_keyset", lambda: (keyset, True))

        key = service.get_key("fake-key-id")
        assert isinstance(key, PyJWK)
        assert key.key_id == "fake-key-id"

        assert metrics.increment.calls == []

    def test_get_key_uncached(self, monkeypatch):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
            cache_url="rediss://fake.example.com",
            metrics=metrics,
        )

        keyset = {
            "fake-key-id": {
                "kid": "fake-key-id",
                "n": "ZHVtbXkK",
                "kty": "RSA",
                "alg": "RS256",
                "e": "AQAB",
                "use": "sig",
                "x5c": ["dummy"],
                "x5t": "dummy",
            }
        }
        monkeypatch.setattr(service, "_get_keyset", lambda: ({}, False))
        monkeypatch.setattr(service, "_refresh_keyset", lambda: keyset)

        key = service.get_key("fake-key-id")
        assert isinstance(key, PyJWK)
        assert key.key_id == "fake-key-id"

        assert metrics.increment.calls == []

    def test_get_key_refresh_fails(self, monkeypatch):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
            cache_url="rediss://fake.example.com",
            metrics=metrics,
        )

        monkeypatch.setattr(service, "_get_keyset", lambda: ({}, False))
        monkeypatch.setattr(service, "_refresh_keyset", lambda: {})

        key = service.get_key("fake-key-id")
        assert key is None

        assert metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.get_key.error",
                tags=["provider:example", "key_id:fake-key-id"],
            )
        ]
