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

import base64
import collections
import json
import time

import pretend
import pytest
import requests

from warehouse.integrations.github import tasks, utils

basic_auth_pypi_1234 = base64.b64encode(b"__token__:pypi-1234").decode("utf-8")


def test_token_leak_matcher_extract():
    with pytest.raises(NotImplementedError):
        utils.TokenLeakMatcher().extract("a")


def test_plain_text_token_leak_matcher_extract():
    assert utils.PlainTextTokenLeakMatcher().extract("a") == "a"


def test_base64_basic_auth_token_leak_extract():
    assert (
        utils.Base64BasicAuthTokenLeakMatcher().extract(basic_auth_pypi_1234)
        == "pypi-1234"
    )


@pytest.mark.parametrize(
    "input", [base64.b64encode(b"pypi-1234").decode("utf-8"), "foo bar"]
)
def test_base64_basic_auth_token_leak_extract_error(input):
    with pytest.raises(utils.ExtractionFailed):
        utils.Base64BasicAuthTokenLeakMatcher().extract(input)


def test_invalid_token_leak_request():
    exc = utils.InvalidTokenLeakRequest("a", "b")

    assert str(exc) == "a"
    assert exc.reason == "b"


@pytest.mark.parametrize(
    "record, error, reason",
    [
        (None, "Record is not a dict but: None", "format"),
        ({}, "Record is missing attribute(s): token, type, url", "format"),
        (
            {"type": "not_found", "token": "a", "url": "b"},
            "Matcher with code not_found not found. "
            "Available codes are: token, base64-basic-auth",
            "invalid_matcher",
        ),
        (
            {"type": "base64-basic-auth", "token": "foo bar", "url": "a"},
            "Cannot extract token from recieved match",
            "extraction",
        ),
    ],
)
def test_token_leak_disclosure_request_from_api_record_error(record, error, reason):
    with pytest.raises(utils.InvalidTokenLeakRequest) as exc:
        utils.TokenLeakDisclosureRequest.from_api_record(record)

    assert str(exc.value) == error
    assert exc.value.reason == reason


@pytest.mark.parametrize(
    "type, token",
    [("token", "pypi-1234"), ("base64-basic-auth", basic_auth_pypi_1234)],
)
def test_token_leak_disclosure_request_from_api_record(type, token):
    request = utils.TokenLeakDisclosureRequest.from_api_record(
        {"type": type, "token": token, "url": "http://example.com"}
    )

    assert request.token == "pypi-1234"
    assert request.public_url == "http://example.com"


class TestGitHubTokenScanningPayloadVerifier:
    def test_init(self):
        metrics = pretend.stub()
        session = pretend.stub()
        token = "api_token"

        verifier = utils.GitHubTokenScanningPayloadVerifier(
            session=session, metrics=metrics, api_token=token
        )

        assert verifier._session is session
        assert verifier._metrics is metrics
        assert verifier._api_token == token

    def test_verify_cache_miss(self):
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
        metrics = pretend.stub(increment=pretend.call_recorder(lambda str: None))
        verifier = utils.GitHubTokenScanningPayloadVerifier(
            session=session, metrics=metrics, api_token="api-token"
        )
        key_id = "90a421169f0a406205f1563a953312f0be898d3c7b6c06b681aa86a874555f4a"
        signature = (
            "MEQCIAfgjgz6Ou/3DXMYZBervz1TKCHFsvwMcbuJhNZse622AiAG86/"
            "cku2XdcmFWNHl2WSJi2fkE8t+auvB24eURaOd2A=="
        )

        payload = (
            '[{"type":"github_oauth_token","token":"cb4985f91f740272c0234202299'
            'f43808034d7f5","url":" https://github.com/github/faketestrepo/blob/'
            'b0dd59c0b500650cacd4551ca5989a6194001b10/production.env"}]'
        )
        assert (
            verifier.verify(payload=payload, key_id=key_id, signature=signature) is True
        )

        assert metrics.increment.calls == [
            pretend.call("warehouse.token_leak.github.auth.cache.miss"),
            pretend.call("warehouse.token_leak.github.auth.success"),
        ]

    def test_verify_cache_hit(self):
        session = pretend.stub()
        metrics = pretend.stub(increment=pretend.call_recorder(lambda str: None))
        verifier = utils.GitHubTokenScanningPayloadVerifier(
            session=session, metrics=metrics, api_token="api-token"
        )
        verifier.public_keys_cached_at = time.time()
        verifier.public_keys_cache = [
            {
                "key_id": "90a421169f0a406205f1563a953312f0be898d3c"
                "7b6c06b681aa86a874555f4a",
                "key": "-----BEGIN PUBLIC KEY-----\n"
                "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE9MJJHnMfn2+H4xL4YaPDA4RpJqU"
                "q\nkCmRCBnYERxZanmcpzQSXs1X/AljlKkbJ8qpVIW4clayyef9gWhFbNHWAA==\n"
                "-----END PUBLIC KEY-----",
            }
        ]

        key_id = "90a421169f0a406205f1563a953312f0be898d3c7b6c06b681aa86a874555f4a"
        signature = (
            "MEQCIAfgjgz6Ou/3DXMYZBervz1TKCHFsvwMcbuJhNZse622AiAG86/"
            "cku2XdcmFWNHl2WSJi2fkE8t+auvB24eURaOd2A=="
        )

        payload = (
            '[{"type":"github_oauth_token","token":"cb4985f91f740272c0234202299'
            'f43808034d7f5","url":" https://github.com/github/faketestrepo/blob/'
            'b0dd59c0b500650cacd4551ca5989a6194001b10/production.env"}]'
        )
        assert (
            verifier.verify(payload=payload, key_id=key_id, signature=signature) is True
        )

        assert metrics.increment.calls == [
            pretend.call("warehouse.token_leak.github.auth.cache.hit"),
            pretend.call("warehouse.token_leak.github.auth.success"),
        ]

    def test_verify_error(self):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda str: None))
        verifier = utils.GitHubTokenScanningPayloadVerifier(
            session=pretend.stub(), metrics=metrics, api_token="api-token"
        )
        verifier._retrieve_public_key_payload = pretend.raiser(
            utils.InvalidTokenLeakRequest("Bla", "bla")
        )

        assert verifier.verify(payload={}, key_id="a", signature="a") is False

        assert metrics.increment.calls == [
            pretend.call("warehouse.token_leak.github.auth.cache.miss"),
            pretend.call("warehouse.token_leak.github.auth.error.bla"),
        ]

    def test_retrieve_public_key_payload(self):
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
        metrics = pretend.stub(increment=pretend.call_recorder(lambda str: None))

        verifier = utils.GitHubTokenScanningPayloadVerifier(
            session=session, metrics=metrics, api_token="api-token"
        )
        assert verifier._retrieve_public_key_payload() == meta_payload
        assert session.get.calls == [
            pretend.call(
                "https://api.github.com/meta/public_keys/token_scanning",
                headers={"Authorization": "token api-token"},
            )
        ]

    def test_get_cached_public_key_cache_hit(self):
        metrics = pretend.stub()
        session = pretend.stub()
        token = "api_token"

        verifier = utils.GitHubTokenScanningPayloadVerifier(
            session=session, metrics=metrics, api_token=token
        )
        verifier.public_keys_cached_at = time.time()
        cache = verifier.public_keys_cache = pretend.stub()

        assert verifier._get_cached_public_keys() is cache

    def test_get_cached_public_key_cache_miss_no_cache(self):
        metrics = pretend.stub()
        session = pretend.stub()
        token = "api_token"

        verifier = utils.GitHubTokenScanningPayloadVerifier(
            session=session, metrics=metrics, api_token=token
        )

        with pytest.raises(utils.CacheMiss):
            verifier._get_cached_public_keys()

    def test_get_cached_public_key_cache_miss_too_old(self):
        metrics = pretend.stub()
        session = pretend.stub()
        token = "api_token"

        verifier = utils.GitHubTokenScanningPayloadVerifier(
            session=session, metrics=metrics, api_token=token
        )
        verifier.public_keys_cache = pretend.stub()

        with pytest.raises(utils.CacheMiss):
            verifier._get_cached_public_keys()

    def test_retrieve_public_key_payload_http_error(self):
        response = pretend.stub(
            status_code=418,
            text="I'm a teapot",
            raise_for_status=pretend.raiser(requests.HTTPError),
        )
        session = pretend.stub(
            get=lambda *a, **k: response,
        )
        verifier = utils.GitHubTokenScanningPayloadVerifier(
            session=session, metrics=pretend.stub(), api_token="api-token"
        )
        with pytest.raises(utils.GitHubPublicKeyMetaAPIError) as exc:
            verifier._retrieve_public_key_payload()

        assert str(exc.value) == "Invalid response code 418: I'm a teapot"
        assert exc.value.reason == "public_key_api.status.418"

    def test_retrieve_public_key_payload_json_error(self):
        response = pretend.stub(
            text="Still a non-json teapot",
            json=pretend.raiser(json.JSONDecodeError("", "", 3)),
            raise_for_status=lambda: None,
        )
        session = pretend.stub(get=lambda *a, **k: response)
        verifier = utils.GitHubTokenScanningPayloadVerifier(
            session=session, metrics=pretend.stub(), api_token="api-token"
        )
        with pytest.raises(utils.GitHubPublicKeyMetaAPIError) as exc:
            verifier._retrieve_public_key_payload()

        assert str(exc.value) == "Non-JSON response received: Still a non-json teapot"
        assert exc.value.reason == "public_key_api.invalid_json"

    def test_retrieve_public_key_payload_connection_error(self):
        session = pretend.stub(get=pretend.raiser(requests.ConnectionError))

        verifier = utils.GitHubTokenScanningPayloadVerifier(
            session=session, metrics=pretend.stub(), api_token="api-token"
        )

        with pytest.raises(utils.GitHubPublicKeyMetaAPIError) as exc:
            verifier._retrieve_public_key_payload()

        assert str(exc.value) == "Could not connect to GitHub"
        assert exc.value.reason == "public_key_api.network_error"

    def test_extract_public_keys(self):
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
        verifier = utils.GitHubTokenScanningPayloadVerifier(
            session=pretend.stub(), metrics=pretend.stub(), api_token="api-token"
        )

        keys = list(verifier._extract_public_keys(pubkey_api_data=meta_payload))

        assert keys == [
            {
                "key": "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcD"
                "QgAE9MJJHnMfn2+H4xL4YaPDA4RpJqUq\nkCmRCBnYERxZanmcpzQSXs1X/AljlKkbJ"
                "8qpVIW4clayyef9gWhFbNHWAA==\n-----END PUBLIC KEY-----",
                "key_id": "90a421169f0a406205f1563a953312f0be"
                "898d3c7b6c06b681aa86a874555f4a",
            }
        ]

    @pytest.mark.parametrize(
        "payload, expected",
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
    def test_extract_public_keys_error(self, payload, expected):
        verifier = utils.GitHubTokenScanningPayloadVerifier(
            session=pretend.stub(), metrics=pretend.stub(), api_token="api-token"
        )

        with pytest.raises(utils.GitHubPublicKeyMetaAPIError) as exc:
            list(verifier._extract_public_keys(pubkey_api_data=payload))

        assert exc.value.reason == "public_key_api.format_error"
        assert str(exc.value) == expected

    def test_check_public_key(self):
        verifier = utils.GitHubTokenScanningPayloadVerifier(
            session=pretend.stub(), metrics=pretend.stub(), api_token="api-token"
        )

        keys = [
            {"key_id": "a", "key": "b"},
            {"key_id": "c", "key": "d"},
        ]
        assert verifier._check_public_key(github_public_keys=keys, key_id="c") == "d"

    def test_check_public_key_error(self):
        verifier = utils.GitHubTokenScanningPayloadVerifier(
            session=pretend.stub(), metrics=pretend.stub(), api_token="api-token"
        )

        with pytest.raises(utils.InvalidTokenLeakRequest) as exc:
            verifier._check_public_key(github_public_keys=[], key_id="c")

        assert str(exc.value) == "Key c not found in github public keys"
        assert exc.value.reason == "wrong_key_id"

    def test_check_signature(self):
        verifier = utils.GitHubTokenScanningPayloadVerifier(
            session=pretend.stub(), metrics=pretend.stub(), api_token="api-token"
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

        payload = (
            '[{"type":"github_oauth_token","token":"cb4985f91f740272c0234202299'
            'f43808034d7f5","url":" https://github.com/github/faketestrepo/blob/'
            'b0dd59c0b500650cacd4551ca5989a6194001b10/production.env"}]'
        )
        assert (
            verifier._check_signature(
                payload=payload, public_key=public_key, signature=signature
            )
            is None
        )

    def test_check_signature_invalid_signature(self):
        verifier = utils.GitHubTokenScanningPayloadVerifier(
            session=pretend.stub(), metrics=pretend.stub(), api_token="api-token"
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

        payload = (
            '[{"type":"github_oauth_token","token":"cb4985f91f740272c0234202299'
            'f43808034d7f5","url":" https://github.com/github/faketestrepo/blob/'
            'b0dd59c0b500650cacd4551ca5989a6194001b10/production.env"}]'
        )
        with pytest.raises(utils.InvalidTokenLeakRequest) as exc:
            verifier._check_signature(
                payload=payload, public_key=public_key, signature=signature
            )

        assert str(exc.value) == "Invalid signature"
        assert exc.value.reason == "invalid_signature"

    def test_check_signature_invalid_crypto(self):
        verifier = utils.GitHubTokenScanningPayloadVerifier(
            session=pretend.stub(), metrics=pretend.stub(), api_token="api-token"
        )
        public_key = ""
        signature = ""

        payload = "yeah, nope, that won't pass"

        with pytest.raises(utils.InvalidTokenLeakRequest) as exc:
            verifier._check_signature(
                payload=payload, public_key=public_key, signature=signature
            )

        assert str(exc.value) == "Invalid cryptographic values"
        assert exc.value.reason == "invalid_crypto"


def test_analyze_disclosure(monkeypatch):

    metrics = collections.Counter()

    def metrics_increment(key):
        metrics.update([key])

    user = pretend.stub()
    database_macaroon = pretend.stub(user=user, id=12)

    check = pretend.call_recorder(lambda *a, **kw: database_macaroon)
    delete = pretend.call_recorder(lambda *a, **kw: None)
    svc = {
        utils.IMetricsService: pretend.stub(increment=metrics_increment),
        utils.IMacaroonService: pretend.stub(
            check_if_macaroon_exists=check, delete_macaroon=delete
        ),
    }

    request = pretend.stub(find_service=lambda iface, context: svc[iface])

    send_email = pretend.call_recorder(lambda *a, **kw: None)
    monkeypatch.setattr(utils, "send_token_compromised_email_leak", send_email)

    utils.analyze_disclosure(
        request=request,
        disclosure_record={
            "type": "token",
            "token": "pypi-1234",
            "url": "http://example.com",
        },
        origin="github",
    )
    assert metrics == {
        "warehouse.token_leak.github.recieved": 1,
        "warehouse.token_leak.github.processed": 1,
        "warehouse.token_leak.github.valid": 1,
    }
    assert send_email.calls == [
        pretend.call(request, user, public_url="http://example.com", origin="github")
    ]
    assert check.calls == [pretend.call(raw_macaroon="pypi-1234")]
    assert delete.calls == [pretend.call(macaroon_id="12")]


def test_analyze_disclosure_wrong_record():

    metrics = collections.Counter()

    def metrics_increment(key):
        metrics.update([key])

    svc = {
        utils.IMetricsService: pretend.stub(increment=metrics_increment),
        utils.IMacaroonService: pretend.stub(),
    }

    request = pretend.stub(find_service=lambda iface, context: svc[iface])

    utils.analyze_disclosure(
        request=request,
        disclosure_record={},
        origin="github",
    )
    assert metrics == {
        "warehouse.token_leak.github.recieved": 1,
        "warehouse.token_leak.github.error.format": 1,
    }


def test_analyze_disclosure_invalid_macaroon():

    metrics = collections.Counter()

    def metrics_increment(key):
        metrics.update([key])

    check = pretend.raiser(utils.InvalidMacaroon("Bla", "bla"))
    svc = {
        utils.IMetricsService: pretend.stub(increment=metrics_increment),
        utils.IMacaroonService: pretend.stub(check_if_macaroon_exists=check),
    }

    request = pretend.stub(find_service=lambda iface, context: svc[iface])

    utils.analyze_disclosure(
        request=request,
        disclosure_record={
            "type": "token",
            "token": "pypi-1234",
            "url": "http://example.com",
        },
        origin="github",
    )
    assert metrics == {
        "warehouse.token_leak.github.recieved": 1,
        "warehouse.token_leak.github.error.invalid": 1,
    }


def test_analyze_disclosure_unknown_error(monkeypatch):

    metrics = collections.Counter()

    def metrics_increment(key):
        metrics.update([key])

    request = pretend.stub(
        find_service=lambda *a, **k: pretend.stub(increment=metrics_increment)
    )
    monkeypatch.setattr(utils, "_analyze_disclosure", pretend.raiser(ValueError()))

    with pytest.raises(ValueError):
        utils.analyze_disclosure(
            request=request,
            disclosure_record={},
            origin="github",
        )
    assert metrics == {
        "warehouse.token_leak.github.error.unknown": 1,
    }


def test_analyze_disclosures_wrong_type():

    metrics = collections.Counter()

    def metrics_increment(key):
        metrics.update([key])

    metrics_service = pretend.stub(increment=metrics_increment)

    with pytest.raises(utils.InvalidTokenLeakRequest) as exc:
        utils.analyze_disclosures(
            disclosure_records={}, origin="yay", metrics=metrics_service
        )

    assert str(exc.value) == "Invalid format: payload is not a list"
    assert exc.value.reason == "format"


def test_analyze_disclosures_raise(monkeypatch):
    metrics = collections.Counter()

    def metrics_increment(key):
        metrics.update([key])

    metrics_service = pretend.stub(increment=metrics_increment)

    task = pretend.stub(delay=pretend.call_recorder(lambda *a, **k: None))

    monkeypatch.setattr(tasks, "analyze_disclosure_task", task)

    utils.analyze_disclosures(
        disclosure_records=[1, 2, 3], origin="yay", metrics=metrics_service
    )

    assert task.delay.calls == [
        pretend.call(disclosure_record=1, origin="yay"),
        pretend.call(disclosure_record=2, origin="yay"),
        pretend.call(disclosure_record=3, origin="yay"),
    ]
