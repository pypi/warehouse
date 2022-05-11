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

import pretend
import pytest

from jwt import PyJWK, PyJWTError
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
        assert verifyClass(
            interfaces.IOIDCProviderService, services.OIDCProviderService
        )

    def test_verify_signature_only(self, monkeypatch):
        service = services.OIDCProviderService(
            provider=pretend.stub(),
            issuer_url=pretend.stub(),
            cache_url=pretend.stub(),
            metrics=pretend.stub(),
        )

        token = pretend.stub()
        decoded = pretend.stub()
        jwt = pretend.stub(decode=pretend.call_recorder(lambda t, **kwargs: decoded))
        monkeypatch.setattr(
            service, "_get_key_for_token", pretend.call_recorder(lambda t: "fake-key")
        )
        monkeypatch.setattr(services, "jwt", jwt)

        assert service._verify_signature_only(token) == decoded
        assert jwt.decode.calls == [
            pretend.call(
                token,
                key="fake-key",
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
                audience="pypi",
                leeway=30,
            )
        ]

    @pytest.mark.parametrize("exc", [PyJWTError, ValueError])
    def test_verify_signature_only_fails(self, monkeypatch, exc):
        service = services.OIDCProviderService(
            provider=pretend.stub(),
            issuer_url=pretend.stub(),
            cache_url=pretend.stub(),
            metrics=pretend.stub(),
        )

        token = pretend.stub()
        jwt = pretend.stub(decode=pretend.raiser(exc), PyJWTError=PyJWTError)
        monkeypatch.setattr(
            service, "_get_key_for_token", pretend.call_recorder(lambda t: "fake-key")
        )
        monkeypatch.setattr(services, "jwt", jwt)

        assert service._verify_signature_only(token) is None

    def test_verify_for_project(self, monkeypatch):
        service = services.OIDCProviderService(
            provider="fakeprovider",
            issuer_url=pretend.stub(),
            cache_url=pretend.stub(),
            metrics=pretend.stub(
                increment=pretend.call_recorder(lambda *a, **kw: None)
            ),
        )

        token = pretend.stub()
        claims = pretend.stub()
        monkeypatch.setattr(
            service, "_verify_signature_only", pretend.call_recorder(lambda t: claims)
        )

        provider = pretend.stub(verify_claims=pretend.call_recorder(lambda c: True))
        project = pretend.stub(name="fakeproject", oidc_providers=[provider])

        assert service.verify_for_project(token, project)
        assert service.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.verify_for_project.attempt",
                tags=["project:fakeproject", "provider:fakeprovider"],
            ),
            pretend.call(
                "warehouse.oidc.verify_for_project.ok",
                tags=["project:fakeproject", "provider:fakeprovider"],
            ),
        ]
        assert service._verify_signature_only.calls == [pretend.call(token)]
        assert provider.verify_claims.calls == [pretend.call(claims)]

    def test_verify_for_project_invalid_signature(self, monkeypatch):
        service = services.OIDCProviderService(
            provider="fakeprovider",
            issuer_url=pretend.stub(),
            cache_url=pretend.stub(),
            metrics=pretend.stub(
                increment=pretend.call_recorder(lambda *a, **kw: None)
            ),
        )

        token = pretend.stub()
        monkeypatch.setattr(service, "_verify_signature_only", lambda t: None)

        project = pretend.stub(name="fakeproject")

        assert not service.verify_for_project(token, project)
        assert service.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.verify_for_project.attempt",
                tags=["project:fakeproject", "provider:fakeprovider"],
            ),
            pretend.call(
                "warehouse.oidc.verify_for_project.invalid_signature",
                tags=["project:fakeproject", "provider:fakeprovider"],
            ),
        ]

    def test_verify_for_project_invalid_claims(self, monkeypatch):
        service = services.OIDCProviderService(
            provider="fakeprovider",
            issuer_url=pretend.stub(),
            cache_url=pretend.stub(),
            metrics=pretend.stub(
                increment=pretend.call_recorder(lambda *a, **kw: None)
            ),
        )

        token = pretend.stub()
        claims = pretend.stub()
        monkeypatch.setattr(
            service, "_verify_signature_only", pretend.call_recorder(lambda t: claims)
        )

        provider = pretend.stub(verify_claims=pretend.call_recorder(lambda c: False))
        project = pretend.stub(name="fakeproject", oidc_providers=[provider])

        assert not service.verify_for_project(token, project)
        assert service.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.verify_for_project.attempt",
                tags=["project:fakeproject", "provider:fakeprovider"],
            ),
            pretend.call(
                "warehouse.oidc.verify_for_project.invalid_claims",
                tags=["project:fakeproject", "provider:fakeprovider"],
            ),
        ]
        assert service._verify_signature_only.calls == [pretend.call(token)]
        assert provider.verify_claims.calls == [pretend.call(claims)]

    def test_get_keyset_not_cached(self, monkeypatch, mockredis):
        service = services.OIDCProviderService(
            provider="example",
            issuer_url=pretend.stub(),
            cache_url="rediss://fake.example.com",
            metrics=pretend.stub(),
        )

        monkeypatch.setattr(services.redis, "StrictRedis", mockredis)

        keys, timeout = service._get_keyset()

        assert not keys
        assert timeout is False

    def test_get_keyset_cached(self, monkeypatch, mockredis):
        service = services.OIDCProviderService(
            provider="example",
            issuer_url=pretend.stub(),
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
        service = services.OIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
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
                "warehouse.oidc.refresh_keyset.timeout", tags=["provider:example"]
            )
        ]

    def test_refresh_keyset_oidc_config_fails(self, monkeypatch, mockredis):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
            cache_url="rediss://fake.example.com",
            metrics=metrics,
        )

        monkeypatch.setattr(services.redis, "StrictRedis", mockredis)

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

    def test_refresh_keyset_oidc_config_no_jwks_uri(self, monkeypatch, mockredis):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
            cache_url="rediss://fake.example.com",
            metrics=metrics,
        )

        monkeypatch.setattr(services.redis, "StrictRedis", mockredis)

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

    def test_refresh_keyset_oidc_config_no_jwks_json(self, monkeypatch, mockredis):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
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

    def test_refresh_keyset_oidc_config_no_jwks_keys(self, monkeypatch, mockredis):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
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

    def test_refresh_keyset_successful(self, monkeypatch, mockredis):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        service = services.OIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
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

        key = service._get_key("fake-key-id")
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

        key = service._get_key("fake-key-id")
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

        key = service._get_key("fake-key-id")
        assert key is None

        assert metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.get_key.error",
                tags=["provider:example", "key_id:fake-key-id"],
            )
        ]

    def test_get_key_for_token(self, monkeypatch):
        token = pretend.stub()
        key = pretend.stub()

        service = services.OIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
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


class TestNullOIDCProviderService:
    def test_warns_on_init(self, monkeypatch):
        warnings = pretend.stub(warn=pretend.call_recorder(lambda m, c: None))
        monkeypatch.setattr(services, "warnings", warnings)

        service = services.NullOIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
            cache_url="rediss://fake.example.com",
            metrics=pretend.stub(),
        )

        assert service is not None
        assert warnings.warn.calls == [
            pretend.call(
                "NullOIDCProviderService is intended only for use in development, "
                "you should not use it in production due to the lack of actual "
                "JWT verification.",
                services.InsecureOIDCProviderWarning,
            )
        ]

    def test_verify_for_project_malformed_jwt(self):
        service = services.NullOIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
            cache_url="rediss://fake.example.com",
            metrics=pretend.stub(),
        )

        assert not service.verify_for_project("malformed-jwt", pretend.stub())

    def test_verify_for_project_missing_aud(self):
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

        service = services.NullOIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
            cache_url="rediss://fake.example.com",
            metrics=pretend.stub(),
        )

        assert not service.verify_for_project(jwt, pretend.stub())

    def test_verify_for_project_wrong_aud(self):
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

        service = services.NullOIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
            cache_url="rediss://fake.example.com",
            metrics=pretend.stub(),
        )

        assert not service.verify_for_project(jwt, pretend.stub())

    def test_verify_for_project(self):
        # {
        #  "iss": "foo",
        #  "iat": 1516239022,
        #  "nbf": 1516239022,
        #  "exp": 9999999999,
        #  "aud": "pypi"
        # }
        jwt = (
            "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJmb28iLCJpYXQiOj"
            "E1MTYyMzkwMjIsIm5iZiI6MTUxNjIzOTAyMiwiZXhwIjo5OTk5OTk5OTk5LCJhd"
            "WQiOiJweXBpIn0.JQF7ozT5RgI3g1b75DACO3rSxD7ZRYzC0yqBpvvUrGoOUQQZ"
            "SfFRc7w9loudk04am2KlLIGjfPum5IITHuiK41XkSFHoTT0fo1aJegHk5_qrk1a"
            "jXlfNa8otN2woORZdGqUUgF01bDB-1uwfcus5cjBNXYiNzIFO3VeRlBTLNIhUNH"
            "5I3KKb5T1tFad46E5H7HyzOG4EVwTPHK1-6a5WB3DmC-ExJW831zPda2VKXaFrl"
            "v3pUZalLOIVulmuvMkw89FrCsm6V5LF5BxbsWn1G5lJAO6XNqPC--xdN3OsloZI"
            "FVi4A1Y23Ni2LwertdzGumDKrQeEUCarOzkQIjckAg"
        )

        service = services.NullOIDCProviderService(
            provider="example",
            issuer_url="https://example.com",
            cache_url="rediss://fake.example.com",
            metrics=pretend.stub(),
        )

        project = pretend.stub(
            oidc_providers=[pretend.stub(verify_claims=lambda c: True)]
        )

        assert service.verify_for_project(jwt, project)
