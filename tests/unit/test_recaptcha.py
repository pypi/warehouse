from os import environ

import pytest
import pretend
import responses

from warehouse import recaptcha


_SETTINGS = {
    "recaptcha": {
        "site_key": "site_key_value",
        "secret_key": "secret_key_value",
    },
}
_REQUEST = pretend.stub(
    registry=pretend.stub(
        settings=_SETTINGS,
    ),
)


class TestVerifyResponse:
    @responses.activate
    def test_unexpected_data_error(self):
        responses.add(
            responses.POST,
            recaptcha.VERIFY_URL,
            body="something awful",
        )
        serv = recaptcha.Service(_REQUEST)
        
        with pytest.raises(recaptcha.UnknownError) as err:
            res = serv.verify_response("meaningless")
            assert str(err) == \
                "Unexpected data in response body: something awful"
    
    @responses.activate
    def test_missing_success_key_error(self):
        responses.add(
            responses.POST,
            recaptcha.VERIFY_URL,
            json={},
        )
        serv = recaptcha.Service(_REQUEST)

        with pytest.raises(recaptcha.UnknownError) as err:
            res = serv.verify_response("meaningless")
            assert str(err) == "Missing 'success' key in response: {}"

    @responses.activate
    def test_error_map_error(self):
        for key, exc_tp in recaptcha.ERROR_CODE_MAP.items():
            responses.add(
                responses.POST,
                recaptcha.VERIFY_URL,
                json={
                    "success": False,
                    "challenge_ts": 0,
                    "hostname": "hotname_value",
                    "error_codes": [key]
                }
            )

            serv = recaptcha.Service(_REQUEST)
            with pytest.raises(exc_tp):
                res = serv.verify_response("meaningless")

            responses.reset()

    @responses.activate
    def test_error_map_unknown_error(self):
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

        serv = recaptcha.Service(_REQUEST)
        with pytest.raises(recaptcha.UnknownError) as err:
            res = serv.verify_response("meaningless")
            assert str(err) == "Unhandled error code: slartibartfast"

    @responses.activate
    def test_challenge_response_missing_timestamp_success(self):
        responses.add(
            responses.POST,
            recaptcha.VERIFY_URL,
            json={
                "success": True,
                "hostname": "hostname_value",
            },
        )

        serv = recaptcha.Service(_REQUEST)
        res = serv.verify_response("meaningless")
        
        assert isinstance(res, recaptcha.ChallengeResponse)
        assert res.challenge_ts is None
        assert res.hostname == "hostname_value"

    @responses.activate
    def test_challenge_response_missing_hostname_success(self):
        responses.add(
            responses.POST,
            recaptcha.VERIFY_URL,
            json={
                "success": True,
                "challenge_ts": 0,
            },
        )

        serv = recaptcha.Service(_REQUEST)
        res = serv.verify_response("meaningless")

        assert isinstance(res, recaptcha.ChallengeResponse)
        assert res.hostname is None
        assert res.challenge_ts == 0

    @responses.activate
    def test_challenge_response_successs(self):
        responses.add(
            responses.POST,
            recaptcha.VERIFY_URL,
            json={
                "success": True,
                "hostname": "hostname_value",
                "challenge_ts": 0,
            },
        )

        serv = recaptcha.Service(_REQUEST)
        res = serv.verify_response("meaningless")

        assert isinstance(res, recaptcha.ChallengeResponse)
        assert res.hostname == "hostname_value"
        assert res.challenge_ts == 0


def test_includeme():
    config = pretend.stub(
        register_service_factory=pretend.call_recorder(
            lambda fact, name: None
        ),
        add_settings=pretend.call_recorder(lambda settings: None),
    )
    recaptcha.includeme(config)
    
    assert config.register_service_factory.calls == [
        pretend.call(recaptcha.service_factory, name="recaptcha"),
    ]

    assert config.add_settings.calls == [
        pretend.call({
            "recaptcha": {
                "site_key": environ.get("RECAPTCHA_SITE_KEY", ""),
                "secret_key": environ.get("RECAPTCHA_SECRET_KEY", ""),
            },
        }),
    ]
