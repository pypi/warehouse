# SPDX-License-Identifier: Apache-2.0

import json
import time
import uuid

import pretend
import pytest
import requests

from warehouse import integrations
from warehouse.events.tags import EventTag
from warehouse.integrations.secrets import tasks, utils


def test_disclosure_origin_serialization(someorigin):
    assert (
        someorigin.to_dict()
        == utils.DisclosureOrigin.from_dict(someorigin.to_dict()).to_dict()
        == {
            "name": "SomeOrigin",
            "key_id_header": "SOME_KEY_ID_HEADER",
            "signature_header": "SOME_SIGNATURE_HEADER",
            "verification_url": "https://some.verification.url",
            "api_token": None,
        }
    )


def test_disclosure_origin_equivalence(someorigin):
    assert someorigin == someorigin
    someotherorigin = utils.DisclosureOrigin(
        name="SomeOtherOrigin",
        key_id_header="SOME_KEY_ID_HEADER",
        signature_header="SOME_SIGNATURE_HEADER",
        verification_url="https://some.verification.url",
        api_token=None,
    )
    assert someorigin != someotherorigin
    assert someorigin != "wu-tang"


def test_token_leak_matcher_extract():
    with pytest.raises(NotImplementedError):
        utils.TokenLeakMatcher().extract("a")


def test_plain_text_token_leak_matcher_extract():
    assert utils.PlainTextTokenLeakMatcher().extract("a") == "a"


def test_invalid_token_leak_request():
    exc = utils.InvalidTokenLeakRequestError("a", "b")

    assert str(exc) == "a"
    assert exc.reason == "b"


@pytest.mark.parametrize(
    ("record", "error", "reason"),
    [
        (None, "Record is not a dict but: None", "format"),
        ({}, "Record is missing attribute(s): token, type, url", "format"),
        (
            {"type": "not_found", "token": "a", "url": "b"},
            "Matcher with code not_found not found. "
            "Available codes are: failer, pypi_api_token",
            "invalid_matcher",
        ),
        (
            {"type": "failer", "token": "a", "url": "b"},
            "Cannot extract token from received match",
            "extraction",
        ),
    ],
)
def test_token_leak_disclosure_request_from_api_record_error(record, error, reason):
    class MyFailingMatcher(utils.TokenLeakMatcher):
        name = "failer"

        def extract(self, text):
            raise utils.ExtractionFailedError()

    with pytest.raises(utils.InvalidTokenLeakRequestError) as exc:
        utils.TokenLeakDisclosureRequest.from_api_record(
            record, matchers={"failer": MyFailingMatcher(), **utils.TOKEN_LEAK_MATCHERS}
        )

    assert str(exc.value) == error
    assert exc.value.reason == reason


@pytest.mark.parametrize("source", [None, "content"])
def test_token_leak_disclosure_request_from_api_record(source):
    api_record = {
        "type": "pypi_api_token",
        "token": "pypi-1234",
        "url": "http://example.com",
    }
    if source:
        api_record["source"] = source

    request = utils.TokenLeakDisclosureRequest.from_api_record(api_record)

    assert request.token == "pypi-1234"
    assert request.public_url == "http://example.com"
    assert request.source == source


class TestGenericTokenScanningPayloadVerifier:

    def test_init(self, metrics, someorigin):
        session = pretend.stub()
        token = "api_token"
        url = "http://foo"
        cache = integrations.PublicKeysCache(cache_time=12)

        generic_verifier = utils.GenericTokenScanningPayloadVerifier(
            origin=someorigin,
            api_url="http://foo",
            session=session,
            metrics=metrics,
            api_token=token,
            public_keys_cache=cache,
        )

        assert generic_verifier._session is session
        assert generic_verifier._metrics is metrics
        assert generic_verifier._api_token == token
        assert generic_verifier._api_url == url
        assert generic_verifier._public_keys_cache is cache

    def test_verify_cache_miss(self, metrics, someorigin):
        # Example taken from
        # https://gist.github.com/ewjoachim/7dde11c31d9686ed6b4431c3ca166da2
        meta_payload = {
            "public_keys": [
                {
                    "key_identifier": "90a421169f0a406205f1563a953312f0be898d3c"
                    "7b6c06b681aa86a874555f4a",
                    "key": "-----BEGIN PUBLIC KEY-----\n"
                    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE9MJJHnMfn2+H4xL4YaPDA4RpJqU"
                    "q\nkCmRCBnYERxZanmcpzQSXs1X/AljlKkbJ8qpVIW4clayyef9gWhFbNHWAA==\n"
                    "-----END PUBLIC KEY-----",
                    "is_current": True,
                }
            ]
        }
        response = pretend.stub(
            json=lambda: meta_payload, raise_for_status=lambda: None
        )
        session = pretend.stub(get=lambda *a, **k: response)
        cache = integrations.PublicKeysCache(cache_time=12)
        generic_verifier = utils.GenericTokenScanningPayloadVerifier(
            origin=someorigin,
            api_url="http://foo",
            session=session,
            metrics=metrics,
            api_token="api-token",
            public_keys_cache=cache,
        )
        key_id = "90a421169f0a406205f1563a953312f0be898d3c7b6c06b681aa86a874555f4a"
        signature = (
            "MEQCIAfgjgz6Ou/3DXMYZBervz1TKCHFsvwMcbuJhNZse622AiAG86/"
            "cku2XdcmFWNHl2WSJi2fkE8t+auvB24eURaOd2A=="
        )
        payload = (
            b'[{"type":"github_oauth_token","token":"cb4985f91f740272c0234202299'
            b'f43808034d7f5","url":" https://github.com/github/faketestrepo/blob/'
            b'b0dd59c0b500650cacd4551ca5989a6194001b10/production.env"}]'
        )

        assert (
            generic_verifier.verify(payload=payload, key_id=key_id, signature=signature)
            is True
        )

        assert metrics.increment.calls == [
            pretend.call("warehouse.token_leak.someorigin.auth.cache.miss"),
            pretend.call("warehouse.token_leak.someorigin.auth.success"),
        ]

    def test_verify_cache_hit(self, metrics, someorigin):
        session = pretend.stub()
        cache = integrations.PublicKeysCache(cache_time=12)
        cache.cached_at = time.time()
        cache.cache = [
            {
                "key_id": "90a421169f0a406205f1563a953312f0be898d3c"
                "7b6c06b681aa86a874555f4a",
                "key": "-----BEGIN PUBLIC KEY-----\n"
                "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE9MJJHnMfn2+H4xL4YaPDA4RpJqU"
                "q\nkCmRCBnYERxZanmcpzQSXs1X/AljlKkbJ8qpVIW4clayyef9gWhFbNHWAA==\n"
                "-----END PUBLIC KEY-----",
            }
        ]
        generic_verifier = utils.GenericTokenScanningPayloadVerifier(
            origin=someorigin,
            api_url="http://foo",
            session=session,
            metrics=metrics,
            api_token="api-token",
            public_keys_cache=cache,
        )

        key_id = "90a421169f0a406205f1563a953312f0be898d3c7b6c06b681aa86a874555f4a"
        signature = (
            "MEQCIAfgjgz6Ou/3DXMYZBervz1TKCHFsvwMcbuJhNZse622AiAG86/"
            "cku2XdcmFWNHl2WSJi2fkE8t+auvB24eURaOd2A=="
        )
        payload = (
            b'[{"type":"github_oauth_token","token":"cb4985f91f740272c0234202299'
            b'f43808034d7f5","url":" https://github.com/github/faketestrepo/blob/'
            b'b0dd59c0b500650cacd4551ca5989a6194001b10/production.env"}]'
        )

        assert (
            generic_verifier.verify(payload=payload, key_id=key_id, signature=signature)
            is True
        )

        assert metrics.increment.calls == [
            pretend.call("warehouse.token_leak.someorigin.auth.cache.hit"),
            pretend.call("warehouse.token_leak.someorigin.auth.success"),
        ]

    def test_verify_error(self, metrics, someorigin):
        cache = integrations.PublicKeysCache(cache_time=12)
        generic_verifier = utils.GenericTokenScanningPayloadVerifier(
            origin=someorigin,
            api_url="http://foo",
            session=pretend.stub(),
            metrics=metrics,
            api_token="api-token",
            public_keys_cache=cache,
        )
        generic_verifier.retrieve_public_key_payload = pretend.raiser(
            integrations.InvalidPayloadSignatureError("Bla", "bla")
        )

        assert generic_verifier.verify(payload={}, key_id="a", signature="a") is False

        assert metrics.increment.calls == [
            pretend.call("warehouse.token_leak.someorigin.auth.cache.miss"),
            pretend.call("warehouse.token_leak.someorigin.auth.error.bla"),
        ]

    def test_headers_auth_no_token(self, someorigin):
        headers = utils.GenericTokenScanningPayloadVerifier(
            origin=someorigin,
            api_url="http://foo",
            session=pretend.stub(),
            metrics=pretend.stub(),
            api_token=None,
            public_keys_cache=pretend.stub(),
        )._headers_auth()
        assert headers == {}

    def test_headers_auth_token(self, someorigin):
        headers = utils.GenericTokenScanningPayloadVerifier(
            origin=someorigin,
            api_url="http://foo",
            session=pretend.stub(),
            metrics=pretend.stub(),
            api_token="api-token",
            public_keys_cache=pretend.stub(),
        )._headers_auth()
        assert headers == {"Authorization": "token api-token"}

    def test_retrieve_public_key_payload(self, metrics, someorigin):
        meta_payload = {
            "public_keys": [
                {
                    "key_identifier": "90a421169f0a406205f1563a953312f0be898d3c"
                    "7b6c06b681aa86a874555f4a",
                    "key": "-----BEGIN PUBLIC KEY-----\n"
                    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE9MJJHnMfn2+H4xL4YaPDA4RpJqU"
                    "q\nkCmRCBnYERxZanmcpzQSXs1X/AljlKkbJ8qpVIW4clayyef9gWhFbNHWAA==\n"
                    "-----END PUBLIC KEY-----",
                    "is_current": True,
                }
            ]
        }
        response = pretend.stub(
            json=lambda: meta_payload, raise_for_status=lambda: None
        )
        session = pretend.stub(get=pretend.call_recorder(lambda *a, **k: response))

        generic_verifier = utils.GenericTokenScanningPayloadVerifier(
            origin=someorigin,
            api_url="http://foo",
            session=session,
            metrics=metrics,
            api_token="api-token",
            public_keys_cache=pretend.stub(),
        )
        assert generic_verifier.retrieve_public_key_payload() == meta_payload
        assert session.get.calls == [
            pretend.call(
                "http://foo",
                headers={"Authorization": "token api-token"},
            )
        ]

    def test_get_cached_public_key_cache_hit(self, someorigin):
        session = pretend.stub()
        cache = integrations.PublicKeysCache(cache_time=12)
        cache_value = pretend.stub()
        cache.set(now=time.time(), value=cache_value)

        generic_verifier = utils.GenericTokenScanningPayloadVerifier(
            origin=someorigin,
            api_url="http://foo",
            session=session,
            metrics=pretend.stub(),
            public_keys_cache=cache,
        )

        assert generic_verifier._get_cached_public_keys() is cache_value

    def test_get_cached_public_key_cache_miss_no_cache(self, someorigin):
        session = pretend.stub()
        cache = integrations.PublicKeysCache(cache_time=12)

        generic_verifier = utils.GenericTokenScanningPayloadVerifier(
            origin=someorigin,
            api_url="http://foo",
            session=session,
            metrics=pretend.stub(),
            public_keys_cache=cache,
        )

        with pytest.raises(integrations.CacheMissError):
            generic_verifier._get_cached_public_keys()

    def test_retrieve_public_key_payload_http_error(self, someorigin):
        response = pretend.stub(
            status_code=418,
            text="I'm a teapot",
            raise_for_status=pretend.raiser(requests.HTTPError),
        )
        session = pretend.stub(
            get=lambda *a, **k: response,
        )
        generic_verifier = utils.GenericTokenScanningPayloadVerifier(
            origin=someorigin,
            api_url="http://foo",
            session=session,
            metrics=pretend.stub(),
            public_keys_cache=pretend.stub(),
        )
        with pytest.raises(utils.GenericPublicKeyMetaAPIError) as exc:
            generic_verifier.retrieve_public_key_payload()

        assert str(exc.value) == "Invalid response code 418: I'm a teapot"
        assert exc.value.reason == "public_key_api.status.418"

    def test_retrieve_public_key_payload_json_error(self, someorigin):
        response = pretend.stub(
            text="Still a non-json teapot",
            json=pretend.raiser(json.JSONDecodeError("", "", 3)),
            raise_for_status=lambda: None,
        )
        session = pretend.stub(get=lambda *a, **k: response)
        generic_verifier = utils.GenericTokenScanningPayloadVerifier(
            origin=someorigin,
            api_url="http://foo",
            session=session,
            metrics=pretend.stub(),
            public_keys_cache=pretend.stub(),
        )
        with pytest.raises(utils.GenericPublicKeyMetaAPIError) as exc:
            generic_verifier.retrieve_public_key_payload()

        assert str(exc.value) == "Non-JSON response received: Still a non-json teapot"
        assert exc.value.reason == "public_key_api.invalid_json"

    def test_retrieve_public_key_payload_connection_error(self, someorigin):
        session = pretend.stub(get=pretend.raiser(requests.ConnectionError))

        generic_verifier = utils.GenericTokenScanningPayloadVerifier(
            origin=someorigin,
            api_url="http://foo",
            session=session,
            metrics=pretend.stub(),
            public_keys_cache=pretend.stub(),
        )

        with pytest.raises(utils.GenericPublicKeyMetaAPIError) as exc:
            generic_verifier.retrieve_public_key_payload()

        assert str(exc.value) == "Could not connect to SomeOrigin"
        assert exc.value.reason == "public_key_api.network_error"

    def test_extract_public_keys(self, someorigin):
        meta_payload = {
            "public_keys": [
                {
                    "key_identifier": "90a421169f0a406205f1563a953312f0be898d3c"
                    "7b6c06b681aa86a874555f4a",
                    "key": "-----BEGIN PUBLIC KEY-----\n"
                    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE9MJJHnMfn2+H4xL4YaPDA4RpJqU"
                    "q\nkCmRCBnYERxZanmcpzQSXs1X/AljlKkbJ8qpVIW4clayyef9gWhFbNHWAA==\n"
                    "-----END PUBLIC KEY-----",
                    "is_current": True,
                }
            ]
        }
        cache = integrations.PublicKeysCache(cache_time=12)
        generic_verifier = utils.GenericTokenScanningPayloadVerifier(
            origin=someorigin,
            api_url="http://foo",
            session=pretend.stub(),
            metrics=pretend.stub(),
            public_keys_cache=cache,
        )

        keys = generic_verifier.extract_public_keys(pubkey_api_data=meta_payload)

        assert keys == [
            {
                "key": "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcD"
                "QgAE9MJJHnMfn2+H4xL4YaPDA4RpJqUq\nkCmRCBnYERxZanmcpzQSXs1X/AljlKkbJ"
                "8qpVIW4clayyef9gWhFbNHWAA==\n-----END PUBLIC KEY-----",
                "key_id": "90a421169f0a406205f1563a953312f0be"
                "898d3c7b6c06b681aa86a874555f4a",
            }
        ]
        assert cache.cache == keys

    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            ([], "Payload is not a dict but: []"),
            ({}, "Payload misses 'public_keys' attribute"),
            ({"public_keys": None}, "Payload 'public_keys' attribute is not a list"),
            ({"public_keys": [None]}, "Key is not a dict but: None"),
            (
                {"public_keys": [{}]},
                "Missing attribute in key: ['key', 'key_identifier']",
            ),
            (
                {"public_keys": [{"key": "a"}]},
                "Missing attribute in key: ['key_identifier']",
            ),
            (
                {"public_keys": [{"key_identifier": "a"}]},
                "Missing attribute in key: ['key']",
            ),
        ],
    )
    def test_extract_public_keys_error(self, payload, expected, someorigin):
        cache = integrations.PublicKeysCache(cache_time=12)
        generic_verifier = utils.GenericTokenScanningPayloadVerifier(
            origin=someorigin,
            api_url="http://foo",
            session=pretend.stub(),
            metrics=pretend.stub(),
            public_keys_cache=cache,
        )

        with pytest.raises(utils.GenericPublicKeyMetaAPIError) as exc:
            list(generic_verifier.extract_public_keys(pubkey_api_data=payload))

        assert exc.value.reason == "public_key_api.format_error"
        assert str(exc.value) == expected
        assert cache.cache is None

    def test_check_public_key(self, someorigin):
        generic_verifier = utils.GenericTokenScanningPayloadVerifier(
            origin=someorigin,
            api_url="http://foo",
            session=pretend.stub(),
            metrics=pretend.stub(),
            public_keys_cache=pretend.stub(),
        )

        keys = [
            {"key_id": "a", "key": "b"},
            {"key_id": "c", "key": "d"},
        ]
        assert generic_verifier._check_public_key(public_keys=keys, key_id="c") == "d"

    def test_check_public_key_error(self, someorigin):
        generic_verifier = utils.GenericTokenScanningPayloadVerifier(
            origin=someorigin,
            api_url="http://foo",
            session=pretend.stub(),
            metrics=pretend.stub(),
            public_keys_cache=pretend.stub(),
        )

        with pytest.raises(integrations.InvalidPayloadSignatureError) as exc:
            generic_verifier._check_public_key(public_keys=[], key_id="c")

        assert str(exc.value) == "Key c not found in public keys"
        assert exc.value.reason == "wrong_key_id"

    @pytest.mark.parametrize(
        ("origin", "payload"),
        [
            (
                "GitHub",
                b'[{"type":"github_oauth_token","token":"cb4985f91f740272c0234202299'
                b'f43808034d7f5","url":" https://github.com/github/faketestrepo/blob/'
                b'b0dd59c0b500650cacd4551ca5989a6194001b10/production.env"}]',
            )
        ],
    )
    def test_check_signature(self, origin, payload):
        generic_verifier = utils.GenericTokenScanningPayloadVerifier(
            origin=origin,
            api_url="http://foo",
            session=pretend.stub(),
            metrics=pretend.stub(),
            public_keys_cache=pretend.stub(),
        )
        public_key = (
            "-----BEGIN PUBLIC KEY-----\n"
            "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE9MJJHnMfn2+H4xL4YaPDA4RpJqU"
            "q\nkCmRCBnYERxZanmcpzQSXs1X/AljlKkbJ8qpVIW4clayyef9gWhFbNHWAA==\n"
            "-----END PUBLIC KEY-----"
        )
        signature = (
            "MEQCIAfgjgz6Ou/3DXMYZBervz1TKCHFsvwMcbuJhNZse622AiAG86/"
            "cku2XdcmFWNHl2WSJi2fkE8t+auvB24eURaOd2A=="
        )

        assert (
            generic_verifier._check_signature(
                payload=payload, public_key=public_key, signature=signature
            )
            is None
        )

    @pytest.mark.parametrize(
        ("origin", "payload"),
        [
            (
                "GitHub",
                b'[{"type":"github_oauth_token","token":"cb4985f91f740272c0234202299'
                b'f43808034d7f5","url":" https://github.com/github/faketestrepo/blob/'
                b'b0dd59c0b500650cacd4551ca5989a6194001b10/production.env"}]',
            )
        ],
    )
    def test_check_signature_invalid_signature(self, origin, payload):
        generic_verifier = utils.GenericTokenScanningPayloadVerifier(
            origin=origin,
            api_url="http://foo",
            session=pretend.stub(),
            metrics=pretend.stub(),
            public_keys_cache=pretend.stub(),
        )
        public_key = (
            "-----BEGIN PUBLIC KEY-----\n"
            "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE9MJJHnMfn2+H4xL4YaPDA4RpJqU"
            "q\nkCmRCBnYERxZanmcpzQSXs1X/AljlKkbJ8qpVIW4clayyef9gWhFbNHWAA==\n"
            "-----END PUBLIC KEY-----"
        )
        # Changed the initial N for an M
        signature = (
            "NEQCIAfgjgz6Ou/3DXMYZBervz1TKCHFsvwMcbuJhNZse622AiAG86/"
            "cku2XdcmFWNHl2WSJi2fkE8t+auvB24eURaOd2A=="
        )

        with pytest.raises(integrations.InvalidPayloadSignatureError) as exc:
            generic_verifier._check_signature(
                payload=payload, public_key=public_key, signature=signature
            )

        assert str(exc.value) == "Invalid signature"
        assert exc.value.reason == "invalid_signature"

    def test_check_signature_invalid_crypto(self, someorigin):
        generic_verifier = utils.GenericTokenScanningPayloadVerifier(
            origin=someorigin,
            api_url="http://foo",
            session=pretend.stub(),
            metrics=pretend.stub(),
            public_keys_cache=pretend.stub(),
        )
        public_key = ""
        signature = ""

        payload = "yeah, nope, that won't pass"

        with pytest.raises(integrations.InvalidPayloadSignatureError) as exc:
            generic_verifier._check_signature(
                payload=payload, public_key=public_key, signature=signature
            )

        assert str(exc.value) == "Invalid cryptographic values"
        assert exc.value.reason == "invalid_crypto"


def test_analyze_disclosure(monkeypatch, metrics, someorigin):
    user_id = uuid.UUID(bytes=b"0" * 16)
    user = pretend.stub(
        id=user_id,
        record_event=pretend.call_recorder(lambda *a, **kw: None),
    )
    database_macaroon = pretend.stub(
        user=user,
        id=12,
        permissions_caveat={"permissions": "user", "version": 1},
        caveats=[],
        description="foo",
    )

    find = pretend.call_recorder(lambda *a, **kw: database_macaroon)
    delete = pretend.call_recorder(lambda *a, **kw: None)
    svc = {
        utils.IMetricsService: metrics,
        utils.IMacaroonService: pretend.stub(
            find_from_raw=find, delete_macaroon=delete
        ),
    }

    request = pretend.stub(
        find_service=lambda iface, context: svc[iface], remote_addr="0.0.0.0"
    )

    send_email = pretend.call_recorder(lambda *a, **kw: None)
    monkeypatch.setattr(utils, "send_token_compromised_email_leak", send_email)

    utils.analyze_disclosure(
        request=request,
        disclosure_record={
            "type": "pypi_api_token",
            "token": "pypi-1234",
            "url": "http://example.com",
        },
        origin=someorigin,
    )
    assert metrics.increment.calls == [
        pretend.call("warehouse.token_leak.someorigin.received"),
        pretend.call("warehouse.token_leak.someorigin.valid"),
        pretend.call("warehouse.token_leak.someorigin.processed"),
    ]
    assert send_email.calls == [
        pretend.call(request, user, public_url="http://example.com", origin=someorigin)
    ]
    assert find.calls == [pretend.call(raw_macaroon="pypi-1234")]
    assert delete.calls == [pretend.call(macaroon_id="12")]
    assert user.record_event.calls == [
        pretend.call(
            tag=EventTag.Account.APITokenRemovedLeak,
            request=request,
            additional={
                "macaroon_id": "12",
                "public_url": "http://example.com",
                "permissions": "user",
                "caveats": [],
                "description": "foo",
                "origin": "SomeOrigin",
            },
        )
    ]


def test_analyze_disclosure_wrong_record(metrics, someorigin):
    svc = {
        utils.IMetricsService: metrics,
        utils.IMacaroonService: pretend.stub(),
    }

    request = pretend.stub(find_service=lambda iface, context: svc[iface])

    utils.analyze_disclosure(
        request=request,
        disclosure_record={},
        origin=someorigin,
    )
    assert metrics.increment.calls == [
        pretend.call("warehouse.token_leak.someorigin.received"),
        pretend.call("warehouse.token_leak.someorigin.error.format"),
    ]


def test_analyze_disclosure_invalid_macaroon(metrics, someorigin):
    find = pretend.raiser(utils.InvalidMacaroonError("Bla", "bla"))
    svc = {
        utils.IMetricsService: metrics,
        utils.IMacaroonService: pretend.stub(find_from_raw=find),
    }

    request = pretend.stub(find_service=lambda iface, context: svc[iface])

    utils.analyze_disclosure(
        request=request,
        disclosure_record={
            "type": "pypi_api_token",
            "token": "pypi-1234",
            "url": "http://example.com",
        },
        origin=someorigin,
    )
    assert metrics.increment.calls == [
        pretend.call("warehouse.token_leak.someorigin.received"),
        pretend.call("warehouse.token_leak.someorigin.error.invalid"),
    ]


def test_analyze_disclosure_unknown_error(metrics, monkeypatch, someorigin):
    request = pretend.stub(find_service=lambda *a, **k: metrics)

    class SpecificError(Exception):
        pass

    monkeypatch.setattr(utils, "_analyze_disclosure", pretend.raiser(SpecificError))

    with pytest.raises(SpecificError):
        utils.analyze_disclosure(
            request=request,
            disclosure_record={},
            origin=someorigin,
        )
    assert metrics.increment.calls == [
        pretend.call("warehouse.token_leak.someorigin.error.unknown"),
    ]


def test_analyze_disclosures_wrong_type(metrics, someorigin):
    with pytest.raises(utils.InvalidTokenLeakRequestError) as exc:
        utils.analyze_disclosures(
            request=pretend.stub(),
            disclosure_records={},
            origin=someorigin,
            metrics=metrics,
        )

    assert str(exc.value) == "Invalid format: payload is not a list"
    assert exc.value.reason == "format"


def test_analyze_disclosures_raise(metrics, monkeypatch, someorigin):
    task = pretend.stub(delay=pretend.call_recorder(lambda *a, **k: None))
    request = pretend.stub(task=lambda x: task)

    monkeypatch.setattr(tasks, "analyze_disclosure_task", task)

    utils.analyze_disclosures(
        request=request,
        disclosure_records=[1, 2, 3],
        origin=someorigin,
        metrics=metrics,
    )

    assert task.delay.calls == [
        pretend.call(disclosure_record=1, origin=someorigin.to_dict()),
        pretend.call(disclosure_record=2, origin=someorigin.to_dict()),
        pretend.call(disclosure_record=3, origin=someorigin.to_dict()),
    ]
