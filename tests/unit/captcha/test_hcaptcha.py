# SPDX-License-Identifier: Apache-2.0

import urllib.parse

import pyramid_retry
import pytest
import requests
import responses

from warehouse.captcha import hcaptcha, interfaces


@pytest.fixture
def captcha_request(pyramid_request):
    """A request with a real requests.Session, which responses intercepts."""
    pyramid_request.http = requests.Session()
    pyramid_request.registry.settings.update(
        {
            "hcaptcha.site_key": "site_key_value",
            "hcaptcha.secret_key": "secret_key_value",
        }
    )
    return pyramid_request


def test_create_captcha_service(captcha_request):
    service = hcaptcha.Service.create_service(
        context=None,
        request=captcha_request,
    )
    assert isinstance(service, hcaptcha.Service)


def test_csp_policy(captcha_request):
    csp_hostnames = ["https://hcaptcha.com", "https://*.hcaptcha.com"]
    service = hcaptcha.Service.create_service(
        context=None,
        request=captcha_request,
    )
    assert service.csp_policy == {
        "script-src": csp_hostnames,
        "frame-src": csp_hostnames,
        "style-src": csp_hostnames,
        "connect-src": csp_hostnames,
    }


def test_enabled(captcha_request):
    service = hcaptcha.Service.create_service(
        context=None,
        request=captcha_request,
    )
    assert service.enabled


class TestVerifyResponse:
    @responses.activate
    def test_verify_service_disabled(self, pyramid_request):
        responses.add(
            responses.POST,
            hcaptcha.VERIFY_URL,
            body="",
        )

        service = hcaptcha.Service.create_service(
            context=None,
            request=pyramid_request,
        )
        assert service.verify_response("") is None
        assert not responses.calls

    @responses.activate
    def test_verify_response_success(self, captcha_request):
        responses.add(
            responses.POST,
            hcaptcha.VERIFY_URL,
            json={
                "success": True,
                "hostname": "hostname_value",
                "challenge_ts": 0,
            },
        )

        service = hcaptcha.Service.create_service(
            context=None,
            request=captcha_request,
        )
        assert service.verify_response("meaningless") == interfaces.ChallengeResponse(
            challenge_ts=0,
            hostname="hostname_value",
        )

    @responses.activate
    def test_remote_ip_added(self, captcha_request):
        responses.add(
            responses.POST,
            hcaptcha.VERIFY_URL,
            json={"success": True},
        )

        service = hcaptcha.Service.create_service(
            context=None,
            request=captcha_request,
        )
        assert service.verify_response(
            "meaningless", remote_ip="someip"
        ) == interfaces.ChallengeResponse(
            challenge_ts=None,
            hostname=None,
        )
        payload = dict(urllib.parse.parse_qsl(responses.calls[0].request.body))
        assert payload["remoteip"] == "someip"

    def test_retries_on_timeout(self, mocker, captcha_request):
        service = hcaptcha.Service.create_service(
            context=None,
            request=captcha_request,
        )
        mocker.patch.object(
            service.request.http, "post", autospec=True, side_effect=requests.Timeout
        )

        with pytest.raises(pyramid_retry.RetryableException):
            service.verify_response("meaningless")

    def test_unexpected_error(self, mocker, captcha_request):
        service = hcaptcha.Service.create_service(
            context=None,
            request=captcha_request,
        )
        mocker.patch.object(
            service.request.http,
            "post",
            autospec=True,
            side_effect=Exception("unexpected error"),
        )

        with pytest.raises(hcaptcha.UnexpectedError) as err:
            service.verify_response("meaningless")

        assert err.value.args == ("unexpected error",)

    @responses.activate
    def test_unexpected_data_error(self, captcha_request):
        responses.add(
            responses.POST,
            hcaptcha.VERIFY_URL,
            body="something awful",
        )
        serv = hcaptcha.Service.create_service(context=None, request=captcha_request)

        with pytest.raises(hcaptcha.UnexpectedError) as err:
            serv.verify_response("meaningless")

        expected = "Unexpected data in response body: something awful"
        assert str(err.value) == expected

    @responses.activate
    def test_missing_success_key(self, captcha_request):
        responses.add(
            responses.POST,
            hcaptcha.VERIFY_URL,
            json={},
        )
        serv = hcaptcha.Service.create_service(context=None, request=captcha_request)

        with pytest.raises(hcaptcha.UnexpectedError) as err:
            serv.verify_response("meaningless")

        expected = "Missing 'success' key in response: {}"
        assert str(err.value) == expected

    @responses.activate
    def test_missing_error_codes_key(self, captcha_request):
        responses.add(
            responses.POST,
            hcaptcha.VERIFY_URL,
            json={"success": False},
        )
        serv = hcaptcha.Service.create_service(context=None, request=captcha_request)

        with pytest.raises(hcaptcha.UnexpectedError) as err:
            serv.verify_response("meaningless")

        expected = "Response missing 'error-codes' key: {'success': False}"
        assert str(err.value) == expected

    @responses.activate
    def test_invalid_error_code(self, captcha_request):
        responses.add(
            responses.POST,
            hcaptcha.VERIFY_URL,
            json={"success": False, "error-codes": ["foo"]},
        )
        serv = hcaptcha.Service.create_service(context=None, request=captcha_request)

        with pytest.raises(hcaptcha.UnexpectedError) as err:
            serv.verify_response("meaningless")

        expected = "Unexpected error code: foo"
        assert str(err.value) == expected

    @responses.activate
    def test_valid_error_code(self, captcha_request):
        responses.add(
            responses.POST,
            hcaptcha.VERIFY_URL,
            json={
                "success": False,
                "error-codes": ["invalid-or-already-seen-response"],
            },
        )
        serv = hcaptcha.Service.create_service(context=None, request=captcha_request)

        with pytest.raises(hcaptcha.InvalidOrAlreadySeenResponseError):
            serv.verify_response("meaningless")
