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

import pretend
import pytest

from warehouse.accounts import utils

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


def test_token_leak_analyzer_analyze_disclosure(monkeypatch):

    metrics = collections.defaultdict(int)

    def metrics_increment(key):
        metrics[key] += 1

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
    monkeypatch.setattr(utils, "send_password_compromised_email_leak", send_email)

    analyzer = utils.TokenLeakAnalyzer(request=request)
    analyzer.analyze_disclosure(
        disclosure_record={
            "type": "token",
            "token": "pypi-1234",
            "url": "http://example.com",
        },
        origin="github",
    )
    assert metrics == {
        "warehouse.token_leak.github.recieved": 1,
        "warehouse.token_leak.github.valid": 1,
    }
    assert send_email.calls == [
        pretend.call(request, user, public_url="http://example.com", origin="github")
    ]
    assert check.calls == [pretend.call(raw_macaroon="pypi-1234")]
    assert delete.calls == [pretend.call(macaroon_id="12")]


def test_token_leak_analyzer_analyze_disclosure_wrong_record():

    metrics = collections.defaultdict(int)

    def metrics_increment(key):
        metrics[key] += 1

    svc = {
        utils.IMetricsService: pretend.stub(increment=metrics_increment),
        utils.IMacaroonService: pretend.stub(),
    }

    request = pretend.stub(find_service=lambda iface, context: svc[iface])

    analyzer = utils.TokenLeakAnalyzer(request=request)
    analyzer.analyze_disclosure(
        disclosure_record={}, origin="github",
    )
    assert metrics == {
        "warehouse.token_leak.github.recieved": 1,
        "warehouse.token_leak.github.error.format": 1,
    }


def test_token_leak_analyzer_analyze_disclosure_invalid_macaroon():

    metrics = collections.defaultdict(int)

    def metrics_increment(key):
        metrics[key] += 1

    check = pretend.raiser(utils.InvalidMacaroon("Bla", "bla"))
    svc = {
        utils.IMetricsService: pretend.stub(increment=metrics_increment),
        utils.IMacaroonService: pretend.stub(check_if_macaroon_exists=check),
    }

    request = pretend.stub(find_service=lambda iface, context: svc[iface])

    analyzer = utils.TokenLeakAnalyzer(request=request)
    analyzer.analyze_disclosure(
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
