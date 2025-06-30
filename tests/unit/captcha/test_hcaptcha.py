# SPDX-License-Identifier: Apache-2.0

import pretend
import pyramid_retry
import pytest
import requests
import responses

from warehouse.captcha import hcaptcha, interfaces

_REQUEST = pretend.stub(
    # returning a real requests.Session object because responses is responsible
    # for mocking that out
    http=requests.Session(),
    registry=pretend.stub(
        settings={
            "hcaptcha.site_key": "site_key_value",
            "hcaptcha.secret_key": "secret_key_value",
        },
    ),
)


def test_create_captcha_service():
    service = hcaptcha.Service.create_service(
        context=None,
        request=_REQUEST,
    )
    assert isinstance(service, hcaptcha.Service)


def test_csp_policy():
    csp_hostnames = ["https://hcaptcha.com", "https://*.hcaptcha.com"]
    service = hcaptcha.Service.create_service(
        context=None,
        request=_REQUEST,
    )
    assert service.csp_policy == {
        "script-src": csp_hostnames,
        "frame-src": csp_hostnames,
        "style-src": csp_hostnames,
        "connect-src": csp_hostnames,
    }


def test_enabled():
    service = hcaptcha.Service.create_service(
        context=None,
        request=_REQUEST,
    )
    assert service.enabled


class TestVerifyResponse:
    @responses.activate
    def test_verify_service_disabled(self):
        responses.add(
            responses.POST,
            hcaptcha.VERIFY_URL,
            body="",
        )

        service = hcaptcha.Service.create_service(
            context=None,
            request=pretend.stub(
                registry=pretend.stub(
                    settings={},
                ),
            ),
        )
        assert service.verify_response("") is None

    @responses.activate
    def test_verify_response_success(self):
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
            request=_REQUEST,
        )
        assert service.verify_response("meaningless") == interfaces.ChallengeResponse(
            challenge_ts=0,
            hostname="hostname_value",
        )

    @responses.activate
    def test_remote_ip_added(self):
        responses.add(
            responses.POST,
            hcaptcha.VERIFY_URL,
            json={"success": True},
        )

        service = hcaptcha.Service.create_service(
            context=None,
            request=_REQUEST,
        )
        assert service.verify_response(
            "meaningless", remote_ip="someip"
        ) == interfaces.ChallengeResponse(
            challenge_ts=None,
            hostname=None,
        )

    def test_retries_on_timeout(self, monkeypatch):
        service = hcaptcha.Service.create_service(
            context=None,
            request=_REQUEST,
        )
        monkeypatch.setattr(
            service.request.http, "post", pretend.raiser(requests.Timeout)
        )

        with pytest.raises(pyramid_retry.RetryableException):
            service.verify_response("meaningless")

    def test_unexpected_error(self, monkeypatch):
        service = hcaptcha.Service.create_service(
            context=None,
            request=_REQUEST,
        )
        monkeypatch.setattr(
            service.request.http, "post", pretend.raiser(Exception("unexpected error"))
        )

        with pytest.raises(hcaptcha.UnexpectedError) as err:
            service.verify_response("meaningless")

        assert err.value.args == ("unexpected error",)

    @responses.activate
    def test_unexpected_data_error(self):
        responses.add(
            responses.POST,
            hcaptcha.VERIFY_URL,
            body="something awful",
        )
        serv = hcaptcha.Service.create_service(context=None, request=_REQUEST)

        with pytest.raises(hcaptcha.UnexpectedError) as err:
            serv.verify_response("meaningless")

        expected = "Unexpected data in response body: something awful"
        assert str(err.value) == expected

    @responses.activate
    def test_missing_success_key(self):
        responses.add(
            responses.POST,
            hcaptcha.VERIFY_URL,
            json={},
        )
        serv = hcaptcha.Service.create_service(context=None, request=_REQUEST)

        with pytest.raises(hcaptcha.UnexpectedError) as err:
            serv.verify_response("meaningless")

        expected = "Missing 'success' key in response: {}"
        assert str(err.value) == expected

    @responses.activate
    def test_missing_error_codes_key(self):
        responses.add(
            responses.POST,
            hcaptcha.VERIFY_URL,
            json={"success": False},
        )
        serv = hcaptcha.Service.create_service(context=None, request=_REQUEST)

        with pytest.raises(hcaptcha.UnexpectedError) as err:
            serv.verify_response("meaningless")

        expected = "Response missing 'error-codes' key: {'success': False}"
        assert str(err.value) == expected

    @responses.activate
    def test_invalid_error_code(self):
        responses.add(
            responses.POST,
            hcaptcha.VERIFY_URL,
            json={"success": False, "error-codes": ["foo"]},
        )
        serv = hcaptcha.Service.create_service(context=None, request=_REQUEST)

        with pytest.raises(hcaptcha.UnexpectedError) as err:
            serv.verify_response("meaningless")

        expected = "Unexpected error code: foo"
        assert str(err.value) == expected

    @responses.activate
    def test_valid_error_code(self):
        responses.add(
            responses.POST,
            hcaptcha.VERIFY_URL,
            json={
                "success": False,
                "error-codes": ["invalid-or-already-seen-response"],
            },
        )
        serv = hcaptcha.Service.create_service(context=None, request=_REQUEST)

        with pytest.raises(hcaptcha.InvalidOrAlreadySeenResponseError):
            serv.verify_response("meaningless")
