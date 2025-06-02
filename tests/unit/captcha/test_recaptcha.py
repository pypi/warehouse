# SPDX-License-Identifier: Apache-2.0

import socket
import urllib.parse

import pretend
import pytest
import requests
import responses

from warehouse.captcha import recaptcha


@pytest.fixture
def session_resetting_request():
    """A pretend request object with a requests.Session that is reset between tests."""
    return pretend.stub(
        # returning a real requests.Session object because responses is responsible
        # for mocking that out
        http=requests.Session(),
        registry=pretend.stub(
            settings={
                "recaptcha.site_key": "site_key_value",
                "recaptcha.secret_key": "secret_key_value",
            },
        ),
    )


class TestVerifyResponse:
    @responses.activate
    def test_verify_service_disabled(self):
        responses.add(
            responses.POST,
            recaptcha.VERIFY_URL,
            body="",
        )
        serv = recaptcha.Service.create_service(
            context=None, request=pretend.stub(registry=pretend.stub(settings={}))
        )
        assert serv.verify_response("") is None
        assert not responses.calls

    @responses.activate
    def test_verify_service_disabled_with_none(self):
        responses.add(
            responses.POST,
            recaptcha.VERIFY_URL,
            body="",
        )
        serv = recaptcha.Service.create_service(
            context=None,
            request=pretend.stub(
                registry=pretend.stub(
                    settings={
                        "recaptcha.site_key": None,
                        "recaptcha.secret_key": None,
                    },
                ),
            ),
        )
        assert serv.verify_response("") is None
        assert not responses.calls

    @responses.activate
    def test_remote_ip_payload(self, session_resetting_request):
        responses.add(
            responses.POST,
            recaptcha.VERIFY_URL,
            json={"success": True},
        )
        serv = recaptcha.Service.create_service(
            context=None, request=session_resetting_request
        )
        serv.verify_response("meaningless", remote_ip="ip")

        payload = dict(urllib.parse.parse_qsl(responses.calls[0].request.body))
        assert payload["remoteip"] == "ip"

    @responses.activate
    def test_unexpected_data_error(self, session_resetting_request):
        responses.add(
            responses.POST,
            recaptcha.VERIFY_URL,
            body="something awful",
        )
        serv = recaptcha.Service.create_service(
            context=None, request=session_resetting_request
        )

        with pytest.raises(recaptcha.UnexpectedError) as err:
            serv.verify_response("meaningless")

        expected = "Unexpected data in response body: something awful"
        assert str(err.value) == expected

    @responses.activate
    def test_missing_success_key_error(self, session_resetting_request):
        responses.add(
            responses.POST,
            recaptcha.VERIFY_URL,
            json={"foo": "bar"},
        )
        serv = recaptcha.Service.create_service(
            context=None, request=session_resetting_request
        )

        with pytest.raises(recaptcha.UnexpectedError) as err:
            serv.verify_response("meaningless")

        expected = "Missing 'success' key in response: {'foo': 'bar'}"
        assert str(err.value) == expected

    @responses.activate
    def test_missing_error_codes_key_error(self, session_resetting_request):
        responses.add(
            responses.POST,
            recaptcha.VERIFY_URL,
            json={"success": False},
        )
        serv = recaptcha.Service.create_service(
            context=None, request=session_resetting_request
        )

        with pytest.raises(recaptcha.UnexpectedError) as err:
            serv.verify_response("meaningless")

        expected = "Response missing 'error-codes' key: {'success': False}"
        assert str(err.value) == expected

    @responses.activate
    def test_error_map_error(self, session_resetting_request):
        for key, exc_tp in recaptcha.ERROR_CODE_MAP.items():
            responses.add(
                responses.POST,
                recaptcha.VERIFY_URL,
                json={
                    "success": False,
                    "challenge_ts": 0,
                    "hostname": "hotname_value",
                    "error_codes": [key],
                },
            )

            serv = recaptcha.Service.create_service(
                context=None, request=session_resetting_request
            )
            with pytest.raises(exc_tp):
                serv.verify_response("meaningless")

            responses.reset()

    @responses.activate
    def test_error_map_unknown_error(self, session_resetting_request):
        responses.add(
            responses.POST,
            recaptcha.VERIFY_URL,
            json={
                "success": False,
                "challenge_ts": 0,
                "hostname": "hostname_value",
                "error_codes": ["slartibartfast"],
            },
        )

        serv = recaptcha.Service.create_service(
            context=None, request=session_resetting_request
        )
        with pytest.raises(recaptcha.UnexpectedError) as err:
            serv.verify_response("meaningless")
        assert str(err.value) == "Unexpected error code: slartibartfast"

    @responses.activate
    def test_challenge_response_missing_timestamp_success(
        self, session_resetting_request
    ):
        responses.add(
            responses.POST,
            recaptcha.VERIFY_URL,
            json={
                "success": True,
                "hostname": "hostname_value",
            },
        )

        serv = recaptcha.Service.create_service(
            context=None, request=session_resetting_request
        )
        res = serv.verify_response("meaningless")

        assert isinstance(res, recaptcha.ChallengeResponse)
        assert res.challenge_ts is None
        assert res.hostname == "hostname_value"

    @responses.activate
    def test_challenge_response_missing_hostname_success(
        self, session_resetting_request
    ):
        responses.add(
            responses.POST,
            recaptcha.VERIFY_URL,
            json={
                "success": True,
                "challenge_ts": 0,
            },
        )

        serv = recaptcha.Service.create_service(
            context=None, request=session_resetting_request
        )
        res = serv.verify_response("meaningless")

        assert isinstance(res, recaptcha.ChallengeResponse)
        assert res.hostname is None
        assert res.challenge_ts == 0

    @responses.activate
    def test_challenge_response_success(self, session_resetting_request):
        responses.add(
            responses.POST,
            recaptcha.VERIFY_URL,
            json={
                "success": True,
                "hostname": "hostname_value",
                "challenge_ts": 0,
            },
        )

        serv = recaptcha.Service.create_service(
            context=None, request=session_resetting_request
        )
        res = serv.verify_response("meaningless")

        assert isinstance(res, recaptcha.ChallengeResponse)
        assert res.hostname == "hostname_value"
        assert res.challenge_ts == 0

    @responses.activate
    def test_unexpected_error(self, session_resetting_request):
        serv = recaptcha.Service.create_service(
            context=None, request=session_resetting_request
        )
        serv.request.http.post = pretend.raiser(socket.error)

        with pytest.raises(recaptcha.UnexpectedError):
            serv.verify_response("meaningless")


class TestCSPPolicy:
    def test_csp_policy(self):
        scheme = "https"
        request = pretend.stub(
            scheme=scheme,
            registry=pretend.stub(
                settings={
                    "recaptcha.site_key": "foo",
                    "recaptcha.secret_key": "bar",
                }
            ),
        )
        serv = recaptcha.Service.create_service(context=None, request=request)
        assert serv.csp_policy == {
            "script-src": [
                "{request.scheme}://www.recaptcha.net/recaptcha/",
                "{request.scheme}://www.gstatic.com/recaptcha/",
                "{request.scheme}://www.gstatic.cn/recaptcha/",
            ],
            "frame-src": ["{request.scheme}://www.recaptcha.net/recaptcha/"],
            "style-src": ["'unsafe-inline'"],
        }


def test_create_service(session_resetting_request):
    svc = recaptcha.Service.create_service(
        context=None, request=session_resetting_request
    )
    assert isinstance(svc, recaptcha.Service)
    assert svc.request is session_resetting_request
