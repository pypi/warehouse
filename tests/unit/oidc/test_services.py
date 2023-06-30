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

import jwt
import pretend
import pytest

from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import DecodeError, PyJWK, PyJWTError, algorithms
from zope.interface.verify import verifyClass

import warehouse.utils.exceptions

from tests.common.db.oidc import GitHubPublisherFactory, PendingGitHubPublisherFactory
from warehouse.oidc import interfaces, services


def test_oidc_publisher_service_factory():
    factory = services.OIDCPublisherServiceFactory(
        publisher="example", issuer_url="https://example.com"
    )

    assert factory.publisher == "example"
    assert factory.issuer_url == "https://example.com"
    assert verifyClass(interfaces.IOIDCPublisherService, factory.service_class)

    metrics = pretend.stub()
    request = pretend.stub(
        db=pretend.stub(),
        registry=pretend.stub(
            settings={
                "oidc.jwk_cache_url": "rediss://another.example.com",
                "warehouse.oidc.audience": "fakeaudience",
            }
        ),
        find_service=lambda *a, **kw: metrics,
    )
    service = factory(pretend.stub(), request)

    assert isinstance(service, factory.service_class)
    assert service.db == request.db
    assert service.publisher == factory.publisher
    assert service.issuer_url == factory.issuer_url
    assert service.audience == "fakeaudience"
    assert service.cache_url == "rediss://another.example.com"
    assert service.metrics == metrics

    assert factory != object()
    assert factory != services.OIDCPublisherServiceFactory(
        publisher="another", issuer_url="https://foo.example.com"
    )


class TestOIDCPublisherService:
    def test_interface_matches(self):
        assert verifyClass(
            interfaces.IOIDCPublisherService, services.OIDCPublisherService
        )

    def test_verify_jwt_signature(self, monkeypatch):
        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher=pretend.stub(),
            issuer_url=pretend.stub(),
            audience="fakeaudience",
            cache_url=pretend.stub(),
            metrics=pretend.stub(),
        )

        token = pretend.stub()
        decoded = pretend.stub()
        jwt = pretend.stub(decode=pretend.call_recorder(lambda t, **kwargs: decoded))
        key = pretend.stub(key="fake-key")
        monkeypatch.setattr(
            service, "_get_key_for_token", pretend.call_recorder(lambda t: key)
        )
        monkeypatch.setattr(services, "jwt", jwt)

        assert service.verify_jwt_signature(token) == decoded
        assert jwt.decode.calls == [
            pretend.call(
                token,
                key=key.key,
                algorithms=["RS256"],
                options=dict(
                    verify_signature=True,
                    require=["iss", "iat", "nbf", "exp", "aud"],
                    verify_iss=True,
                    verify_iat=True,
                    verify_nbf=True,
                    verify_exp=True,
                    verify_aud=True,
                ),
                issuer=service.issuer_url,
                audience="fakeaudience",
                leeway=30,
            )
        ]

    @pytest.mark.parametrize("exc", [DecodeError, TypeError("foo")])
    def test_verify_jwt_signature_get_key_for_token_fails(self, monkeypatch, exc):
        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher="fakepublisher",
            issuer_url=pretend.stub(),
            audience="fakeaudience",
            cache_url=pretend.stub(),
            metrics=pretend.stub(
                increment=pretend.call_recorder(lambda *a, **kw: None)
            ),
        )

        token = pretend.stub()
        jwt = pretend.stub(decode=pretend.raiser(exc), PyJWTError=PyJWTError)
        monkeypatch.setattr(service, "_get_key_for_token", pretend.raiser(exc))
        monkeypatch.setattr(services, "jwt", jwt)
        monkeypatch.setattr(
            services.sentry_sdk,
            "capture_message",
            pretend.call_recorder(lambda s: None),
        )

        assert service.verify_jwt_signature(token) is None
        assert service.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.verify_jwt_signature.malformed_jwt",
                tags=["publisher:fakepublisher"],
            )
        ]

        if exc != DecodeError:
            assert services.sentry_sdk.capture_message.calls == [
                pretend.call(f"JWT backend raised generic error: {exc}")
            ]
        else:
            assert services.sentry_sdk.capture_message.calls == []

    @pytest.mark.parametrize("exc", [PyJWTError, TypeError("foo")])
    def test_verify_jwt_signature_fails(self, monkeypatch, exc):
        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher="fakepublisher",
            issuer_url=pretend.stub(),
            audience="fakeaudience",
            cache_url=pretend.stub(),
            metrics=pretend.stub(
                increment=pretend.call_recorder(lambda *a, **kw: None)
            ),
        )

        token = pretend.stub()
        jwt = pretend.stub(decode=pretend.raiser(exc), PyJWTError=PyJWTError)
        key = pretend.stub(key="fake-key")
        monkeypatch.setattr(
            service, "_get_key_for_token", pretend.call_recorder(lambda t: key)
        )
        monkeypatch.setattr(services, "jwt", jwt)
        monkeypatch.setattr(
            services.sentry_sdk,
            "capture_message",
            pretend.call_recorder(lambda s: None),
        )

        assert service.verify_jwt_signature(token) is None
        assert service.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.verify_jwt_signature.invalid_signature",
                tags=["publisher:fakepublisher"],
            )
        ]

        if exc != PyJWTError:
            assert services.sentry_sdk.capture_message.calls == [
                pretend.call(f"JWT backend raised generic error: {exc}")
            ]
        else:
            assert services.sentry_sdk.capture_message.calls == []

    def test_find_publisher(self, monkeypatch):
        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher="fakepublisher",
            issuer_url=pretend.stub(),
            audience="fakeaudience",
            cache_url=pretend.stub(),
            metrics=pretend.stub(
                increment=pretend.call_recorder(lambda *a, **kw: None)
            ),
        )

        token = pretend.stub()

        publisher = pretend.stub(verify_claims=pretend.call_recorder(lambda c: True))
        find_publisher_by_issuer = pretend.call_recorder(lambda *a, **kw: publisher)
        monkeypatch.setattr(
            services, "find_publisher_by_issuer", find_publisher_by_issuer
        )

        assert service.find_publisher(token) == publisher
        assert service.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.find_publisher.attempt",
                tags=["publisher:fakepublisher"],
            ),
            pretend.call(
                "warehouse.oidc.find_publisher.ok",
                tags=["publisher:fakepublisher"],
            ),
        ]

    def test_find_publisher_issuer_lookup_fails(self, monkeypatch):
        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher="fakepublisher",
            issuer_url=pretend.stub(),
            audience="fakeaudience",
            cache_url=pretend.stub(),
            metrics=pretend.stub(
                increment=pretend.call_recorder(lambda *a, **kw: None)
            ),
        )

        find_publisher_by_issuer = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            services, "find_publisher_by_issuer", find_publisher_by_issuer
        )

        claims = pretend.stub()
        assert service.find_publisher(claims) is None
        assert service.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.find_publisher.attempt",
                tags=["publisher:fakepublisher"],
            ),
            pretend.call(
                "warehouse.oidc.find_publisher.publisher_not_found",
                tags=["publisher:fakepublisher"],
            ),
        ]

    def test_find_publisher_verify_claims_fails(self, monkeypatch):
        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher="fakepublisher",
            issuer_url=pretend.stub(),
            audience="fakeaudience",
            cache_url=pretend.stub(),
            metrics=pretend.stub(
                increment=pretend.call_recorder(lambda *a, **kw: None)
            ),
        )

        publisher = pretend.stub(verify_claims=pretend.call_recorder(lambda c: False))
        find_publisher_by_issuer = pretend.call_recorder(lambda *a, **kw: publisher)
        monkeypatch.setattr(
            services, "find_publisher_by_issuer", find_publisher_by_issuer
        )

        claims = pretend.stub()
        assert service.find_publisher(claims) is None
        assert service.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.find_publisher.attempt",
                tags=["publisher:fakepublisher"],
            ),
            pretend.call(
                "warehouse.oidc.find_publisher.invalid_claims",
                tags=["publisher:fakepublisher"],
            ),
        ]
        assert publisher.verify_claims.calls == [pretend.call(claims)]

    def test_get_keyset_not_cached(self, monkeypatch, mockredis):
        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url=pretend.stub(),
            audience="fakeaudience",
            cache_url="rediss://fake.example.com",
            metrics=pretend.stub(),
        )

        monkeypatch.setattr(services.redis, "StrictRedis", mockredis)

        keys, timeout = service._get_keyset()

        assert not keys
        assert timeout is False

    def test_get_keyset_cached(self, monkeypatch, mockredis):
        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url=pretend.stub(),
            audience="fakeaudience",
            cache_url="rediss://fake.example.com",
            metrics=pretend.stub(),
        )

        monkeypatch.setattr(services.redis, "StrictRedis", mockredis)

        keyset = {"fake-key-id": {"foo": "bar"}}
        service._store_keyset(keyset)
        keys, timeout = service._get_keyset()

        assert keys == keyset
        assert timeout is True

    def test_refresh_keyset_timeout(self, monkeypatch, mockredis):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url="https://example.com",
            audience="fakeaudience",
            cache_url="rediss://fake.example.com",
            metrics=metrics,
        )

        monkeypatch.setattr(services.redis, "StrictRedis", mockredis)

        keyset = {"fake-key-id": {"foo": "bar"}}
        service._store_keyset(keyset)

        keys = service._refresh_keyset()
        assert keys == keyset
        assert metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.refresh_keyset.timeout", tags=["publisher:example"]
            )
        ]

    def test_refresh_keyset_oidc_config_fails(self, monkeypatch, mockredis):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url="https://example.com",
            audience="fakeaudience",
            cache_url="rediss://fake.example.com",
            metrics=metrics,
        )

        monkeypatch.setattr(services.redis, "StrictRedis", mockredis)

        requests = pretend.stub(
            get=pretend.call_recorder(lambda url, timeout: pretend.stub(ok=False))
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
            pretend.call(
                "https://example.com/.well-known/openid-configuration", timeout=5
            )
        ]
        assert sentry_sdk.capture_message.calls == [
            pretend.call(
                "OIDC publisher example failed to return configuration: "
                "https://example.com/.well-known/openid-configuration"
            )
        ]

    def test_refresh_keyset_oidc_config_no_jwks_uri(self, monkeypatch, mockredis):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url="https://example.com",
            audience="fakeaudience",
            cache_url="rediss://fake.example.com",
            metrics=metrics,
        )

        monkeypatch.setattr(services.redis, "StrictRedis", mockredis)

        requests = pretend.stub(
            get=pretend.call_recorder(
                lambda url, timeout: pretend.stub(ok=True, json=lambda: {})
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
            pretend.call(
                "https://example.com/.well-known/openid-configuration", timeout=5
            )
        ]
        assert sentry_sdk.capture_message.calls == [
            pretend.call(
                "OIDC publisher example is returning malformed configuration "
                "(no jwks_uri)"
            )
        ]

    def test_refresh_keyset_oidc_config_no_jwks_json(self, monkeypatch, mockredis):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url="https://example.com",
            audience="fakeaudience",
            cache_url="rediss://fake.example.com",
            metrics=metrics,
        )

        monkeypatch.setattr(services.redis, "StrictRedis", mockredis)

        openid_resp = pretend.stub(
            ok=True,
            json=lambda: {
                "jwks_uri": "https://example.com/.well-known/jwks.json",
            },
        )
        jwks_resp = pretend.stub(ok=False)

        def get(url, timeout=5):
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
            pretend.call(
                "https://example.com/.well-known/openid-configuration", timeout=5
            ),
            pretend.call("https://example.com/.well-known/jwks.json", timeout=5),
        ]
        assert sentry_sdk.capture_message.calls == [
            pretend.call(
                "OIDC publisher example failed to return JWKS JSON: "
                "https://example.com/.well-known/jwks.json"
            )
        ]

    def test_refresh_keyset_oidc_config_no_jwks_keys(self, monkeypatch, mockredis):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url="https://example.com",
            audience="fakeaudience",
            cache_url="rediss://fake.example.com",
            metrics=metrics,
        )

        monkeypatch.setattr(services.redis, "StrictRedis", mockredis)

        openid_resp = pretend.stub(
            ok=True,
            json=lambda: {
                "jwks_uri": "https://example.com/.well-known/jwks.json",
            },
        )
        jwks_resp = pretend.stub(ok=True, json=lambda: {})

        def get(url, timeout=5):
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
            pretend.call(
                "https://example.com/.well-known/openid-configuration", timeout=5
            ),
            pretend.call("https://example.com/.well-known/jwks.json", timeout=5),
        ]
        assert sentry_sdk.capture_message.calls == [
            pretend.call("OIDC publisher example returned JWKS JSON but no keys")
        ]

    def test_refresh_keyset_successful(self, monkeypatch, mockredis):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url="https://example.com",
            audience="fakeaudience",
            cache_url="rediss://fake.example.com",
            metrics=metrics,
        )

        monkeypatch.setattr(services.redis, "StrictRedis", mockredis)

        openid_resp = pretend.stub(
            ok=True,
            json=lambda: {
                "jwks_uri": "https://example.com/.well-known/jwks.json",
            },
        )
        jwks_resp = pretend.stub(
            ok=True, json=lambda: {"keys": [{"kid": "fake-key-id", "foo": "bar"}]}
        )

        def get(url, timeout=5):
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
            pretend.call(
                "https://example.com/.well-known/openid-configuration", timeout=5
            ),
            pretend.call("https://example.com/.well-known/jwks.json", timeout=5),
        ]
        assert sentry_sdk.capture_message.calls == []

        # Ensure that we also cached the updated keyset as part of refreshing.
        keys, timeout = service._get_keyset()
        assert keys == {"fake-key-id": {"kid": "fake-key-id", "foo": "bar"}}
        assert timeout is True

    def test_get_key_cached(self, monkeypatch):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url="https://example.com",
            audience="fakeaudience",
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

        key = service._get_key("fake-key-id")
        assert isinstance(key, PyJWK)
        assert key.key_id == "fake-key-id"

        assert metrics.increment.calls == []

    def test_get_key_uncached(self, monkeypatch):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url="https://example.com",
            audience="fakeaudience",
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

        key = service._get_key("fake-key-id")
        assert isinstance(key, PyJWK)
        assert key.key_id == "fake-key-id"

        assert metrics.increment.calls == []

    def test_get_key_refresh_fails(self, monkeypatch):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url="https://example.com",
            audience="fakeaudience",
            cache_url="rediss://fake.example.com",
            metrics=metrics,
        )

        monkeypatch.setattr(service, "_get_keyset", lambda: ({}, False))
        monkeypatch.setattr(service, "_refresh_keyset", lambda: {})

        key = service._get_key("fake-key-id")
        assert key is None

        assert metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.get_key.error",
                tags=["publisher:example", "key_id:fake-key-id"],
            )
        ]

    def test_get_key_for_token(self, monkeypatch):
        token = pretend.stub()
        key = pretend.stub()

        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url="https://example.com",
            audience="fakeaudience",
            cache_url="rediss://fake.example.com",
            metrics=pretend.stub(),
        )
        monkeypatch.setattr(service, "_get_key", pretend.call_recorder(lambda kid: key))

        monkeypatch.setattr(
            services.jwt,
            "get_unverified_header",
            pretend.call_recorder(lambda token: {"kid": "fake-key-id"}),
        )

        assert service._get_key_for_token(token) == key
        assert service._get_key.calls == [pretend.call("fake-key-id")]
        assert services.jwt.get_unverified_header.calls == [pretend.call(token)]

    def test_reify_publisher(self, monkeypatch):
        service = services.OIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url="https://example.com",
            audience="fakeaudience",
            cache_url="rediss://fake.example.com",
            metrics=pretend.stub(),
        )

        publisher = pretend.stub()
        pending_publisher = pretend.stub(
            reify=pretend.call_recorder(lambda *a: publisher)
        )
        project = pretend.stub(
            oidc_publishers=[],
        )

        assert service.reify_pending_publisher(pending_publisher, project) == publisher
        assert pending_publisher.reify.calls == [pretend.call(service.db)]
        assert project.oidc_publishers == [publisher]


class TestNullOIDCPublisherService:
    def test_interface_matches(self):
        assert verifyClass(
            interfaces.IOIDCPublisherService, services.NullOIDCPublisherService
        )

    def test_warns_on_init(self, monkeypatch):
        warnings = pretend.stub(warn=pretend.call_recorder(lambda m, c: None))
        monkeypatch.setattr(services, "warnings", warnings)

        service = services.NullOIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url="https://example.com",
            audience="fakeaudience",
            cache_url="rediss://fake.example.com",
            metrics=pretend.stub(),
        )

        assert service is not None
        assert warnings.warn.calls == [
            pretend.call(
                "NullOIDCPublisherService is intended only for use in development, "
                "you should not use it in production due to the lack of actual "
                "JWT verification.",
                warehouse.utils.exceptions.InsecureOIDCPublisherWarning,
            )
        ]

    def test_verify_jwt_signature_malformed_jwt(self):
        service = services.NullOIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url="https://example.com",
            audience="fakeaudience",
            cache_url="rediss://fake.example.com",
            metrics=pretend.stub(),
        )

        assert service.verify_jwt_signature("malformed-jwt") is None

    def test_verify_jwt_signature_missing_aud(self):
        # {
        #   "iss": "foo",
        #   "iat": 1516239022,
        #   "nbf": 1516239022,
        #   "exp": 9999999999
        #  }
        jwt = (
            "eyJhbGciOiJSUzI1NiJ9.eyJpc3MiOiJmb28iLCJpYXQiOjE1MTYyMzkwMjIsIm5iZ"
            "iI6MTUxNjIzOTAyMiwiZXhwIjo5OTk5OTk5OTk5fQ.CAR9tx9_A6kxIDYWzXotuLfQ"
            "0wmvHDDO98rLO4F46y7QDWOalIok9yX3OzkWz-30TIBl1dleGVYbtZQzFNEJY13OLB"
            "gzFvxEpsAWvKJGyOLz-YDeGd2ApEZaggLvJiPZCngxFTH5fAyEcUUxQs5sCO9lGbkc"
            "E6lg_Di3VQhPohSuj_V7-DkcXefL3lV7m_JNOBoDWx_nDOFx4w2f8Z2NmswMrsu1vU"
            "NUZH7POiQBeyEsbY1at3u6gGerjyeYl8SIbeeRUWL0rtWxTgktoiKKgyPI-8F8Fpug"
            "jwtKZU_WFhIF4nA0les81hxnm8HFnoun2kx5cSF4Db3N8h6m8wRTUw"
        )

        service = services.NullOIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url="https://example.com",
            audience="fakeaudience",
            cache_url="rediss://fake.example.com",
            metrics=pretend.stub(),
        )

        assert service.verify_jwt_signature(jwt) is None

    def test_verify_jwt_signature_wrong_aud(self):
        # {
        #   "iss": "foo",
        #   "iat": 1516239022,
        #   "nbf": 1516239022,
        #   "exp": 9999999999,
        #   "aud": "notpypi"
        # }
        jwt = (
            "eyJhbGciOiJSUzI1NiJ9.eyJpc3MiOiJmb28iLCJpYXQiOjE1MTYyMzkwMjIsIm5iZ"
            "iI6MTUxNjIzOTAyMiwiZXhwIjo5OTk5OTk5OTk5LCJhdWQiOiJub3RweXBpIn0.rFf"
            "rBXfGyRjU-tIo9dpJRkbnB2BLKK6uwjrE6g4pqwN-5BDn_UNR1Cw4t6Pw8kYOCRmVD"
            "aacu01L-GwHaXJmXyKsqIGie-bcp40zn1FX7dP000PQkAdhuQ-lILGhzscWNJK0J_g"
            "IewoFV9jNUVHJmK9UXx0hHl4eaH_3Ob22kzzIqNKuao2625qfLAdNfV44efArEubXT"
            "vBR-Y8HFzj7-7Zz7rHApImFYmC4E1aMDn_XEYJsXaJcwhhXJx8WB8SAhD7JZ-zotrd"
            "hlqkRMD9rXpv4DAMU15SEnw19tztVRf9OA4PO5Hd4uTKxPA1euBJgXa2g9QgIc1aFA"
            "FYKICTVgQ"
        )

        service = services.NullOIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url="https://example.com",
            audience="fakeaudience",
            cache_url="rediss://fake.example.com",
            metrics=pretend.stub(),
        )

        assert service.verify_jwt_signature(jwt) is None

    def test_find_publisher(self, monkeypatch):
        claims = {
            "iss": "foo",
            "iat": 1516239022,
            "nbf": 1516239022,
            "exp": 9999999999,
            "aud": "pypi",
        }

        service = services.NullOIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url="https://example.com",
            audience="pypi",
            cache_url="rediss://fake.example.com",
            metrics=pretend.stub(),
        )

        publisher = pretend.stub(verify_claims=pretend.call_recorder(lambda c: True))
        find_publisher_by_issuer = pretend.call_recorder(lambda *a, **kw: publisher)
        monkeypatch.setattr(
            services, "find_publisher_by_issuer", find_publisher_by_issuer
        )

        assert service.find_publisher(claims) == publisher

    def test_find_publisher_full_pending(self, oidc_service):
        pending_publisher = PendingGitHubPublisherFactory.create(
            project_name="does-not-exist",
            repository_name="bar",
            repository_owner="foo",
            repository_owner_id="123",
            workflow_filename="example.yml",
            environment=None,
        )

        claims = {
            "jti": "6e67b1cb-2b8d-4be5-91cb-757edb2ec970",
            "sub": "repo:foo/bar",
            "aud": "pypi",
            "ref": "fake",
            "sha": "fake",
            "repository": "foo/bar",
            "repository_owner": "foo",
            "repository_owner_id": "123",
            "run_id": "fake",
            "run_number": "fake",
            "run_attempt": "1",
            "repository_id": "fake",
            "actor_id": "fake",
            "actor": "foo",
            "workflow": "fake",
            "head_ref": "fake",
            "base_ref": "fake",
            "event_name": "fake",
            "ref_type": "fake",
            "environment": "fake",
            "job_workflow_ref": "foo/bar/.github/workflows/example.yml@fake",
            "iss": "https://token.actions.githubusercontent.com",
            "nbf": 1650663265,
            "exp": 1650664165,
            "iat": 1650663865,
        }

        expected_pending_publisher = oidc_service.find_publisher(claims, pending=True)
        assert expected_pending_publisher == pending_publisher

    def test_find_publisher_full(self, oidc_service):
        publisher = GitHubPublisherFactory.create(
            repository_name="bar",
            repository_owner="foo",
            repository_owner_id="123",
            workflow_filename="example.yml",
            environment=None,
        )

        claims = {
            "jti": "6e67b1cb-2b8d-4be5-91cb-757edb2ec970",
            "sub": "repo:foo/bar",
            "aud": "pypi",
            "ref": "fake",
            "sha": "fake",
            "repository": "foo/bar",
            "repository_owner": "foo",
            "repository_owner_id": "123",
            "run_id": "fake",
            "run_number": "fake",
            "run_attempt": "1",
            "repository_id": "fake",
            "actor_id": "fake",
            "actor": "foo",
            "workflow": "fake",
            "head_ref": "fake",
            "base_ref": "fake",
            "event_name": "fake",
            "ref_type": "fake",
            "environment": "fake",
            "job_workflow_ref": "foo/bar/.github/workflows/example.yml@fake",
            "iss": "https://token.actions.githubusercontent.com",
            "nbf": 1650663265,
            "exp": 1650664165,
            "iat": 1650663865,
        }

        expected_publisher = oidc_service.find_publisher(claims, pending=False)
        assert expected_publisher == publisher

    def test_reify_publisher(self):
        service = services.NullOIDCPublisherService(
            session=pretend.stub(),
            publisher="example",
            issuer_url="https://example.com",
            audience="fakeaudience",
            cache_url="rediss://fake.example.com",
            metrics=pretend.stub(),
        )

        publisher = pretend.stub()
        pending_publisher = pretend.stub(
            reify=pretend.call_recorder(lambda *a: publisher)
        )
        project = pretend.stub(
            oidc_publishers=[],
        )

        assert service.reify_pending_publisher(pending_publisher, project) == publisher
        assert pending_publisher.reify.calls == [pretend.call(service.db)]
        assert project.oidc_publishers == [publisher]


class TestPyJWTBackstop:
    """
    "Backstop" tests against unexpected PyJWT API changes.
    """

    def test_decodes_token_bare_key(self):
        privkey = rsa.generate_private_key(65537, 2048)
        pubkey = privkey.public_key()

        # Bare cryptography key objects work.
        token = jwt.encode({"foo": "bar"}, privkey, algorithm="RS256")
        decoded = jwt.decode(token, pubkey, algorithms=["RS256"])

        assert decoded == {"foo": "bar"}

    def test_decodes_token_jwk_roundtrip(self):
        privkey = rsa.generate_private_key(65537, 2048)
        pubkey = privkey.public_key()

        privkey_jwk = PyJWK.from_json(algorithms.RSAAlgorithm.to_jwk(privkey))
        pubkey_jwk = PyJWK.from_json(algorithms.RSAAlgorithm.to_jwk(pubkey))

        # Each PyJWK's `key` attribute works.
        token = jwt.encode({"foo": "bar"}, privkey_jwk.key, algorithm="RS256")
        decoded = jwt.decode(token, pubkey_jwk.key, algorithms=["RS256"])

        assert decoded == {"foo": "bar"}

    def test_decodes_token_typeerror_on_pyjwk(self):
        privkey = rsa.generate_private_key(65537, 2048)
        pubkey = privkey.public_key()

        privkey_jwk = PyJWK.from_json(algorithms.RSAAlgorithm.to_jwk(privkey))
        pubkey_jwk = PyJWK.from_json(algorithms.RSAAlgorithm.to_jwk(pubkey))

        token = jwt.encode({"foo": "bar"}, privkey_jwk.key, algorithm="RS256")

        # Passing a `PyJWK` directly into `jwt.decode` does not work.
        with pytest.raises(TypeError, match=r"Expecting a PEM-formatted key\."):
            jwt.decode(token, pubkey_jwk, algorithms=["RS256"])
