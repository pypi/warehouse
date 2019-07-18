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
import webauthn as pywebauthn

import warehouse.utils.webauthn as webauthn


def test_generate_webauthn_challenge():
    challenge = webauthn.generate_webauthn_challenge()

    assert isinstance(challenge, str)
    assert (
        challenge
        == webauthn._webauthn_b64encode(
            webauthn._webauthn_b64decode(challenge)
        ).decode()
    )


def test_verify_registration_response(monkeypatch):
    response_obj = pretend.stub(
        verify=pretend.call_recorder(lambda: "not a real object")
    )
    response_cls = pretend.call_recorder(lambda *a, **kw: response_obj)
    monkeypatch.setattr(pywebauthn, "WebAuthnRegistrationResponse", response_cls)

    resp = webauthn.verify_registration_response(
        {}, "not_a_real_challenge", rp_id="fake_rp_id", origin="fake_origin"
    )

    assert response_cls.calls == [
        pretend.call(
            "fake_rp_id",
            "fake_origin",
            {},
            webauthn._webauthn_b64encode("not_a_real_challenge".encode()).decode(),
            self_attestation_permitted=True,
        )
    ]
    assert resp == "not a real object"


def test_verify_registration_response_failure(monkeypatch):
    response_obj = pretend.stub(
        verify=pretend.raiser(pywebauthn.webauthn.RegistrationRejectedException)
    )
    response_cls = pretend.call_recorder(lambda *a, **kw: response_obj)
    monkeypatch.setattr(pywebauthn, "WebAuthnRegistrationResponse", response_cls)

    with pytest.raises(webauthn.RegistrationRejectedException):
        webauthn.verify_registration_response(
            {}, "not_a_real_challenge", rp_id="fake_rp_id", origin="fake_origin"
        )


def test_verify_assertion_response(monkeypatch):
    assertion_obj = pretend.stub(verify=pretend.call_recorder(lambda: 1234))
    assertion_cls = pretend.call_recorder(lambda *a, **kw: assertion_obj)
    monkeypatch.setattr(pywebauthn, "WebAuthnAssertionResponse", assertion_cls)

    not_a_real_user = pretend.stub(credential_id="not_a_real_credential")
    get_webauthn_users = pretend.call_recorder(lambda *a, **kw: [not_a_real_user])
    monkeypatch.setattr(webauthn, "_get_webauthn_users", get_webauthn_users)

    not_a_real_assertion = object()
    resp = webauthn.verify_assertion_response(
        not_a_real_assertion,
        challenge="not_a_real_challenge",
        user=not_a_real_user,
        origin="fake_origin",
        icon_url="fake_icon_url",
        rp_id="fake_rp_id",
    )

    assert get_webauthn_users.calls == [
        pretend.call(not_a_real_user, icon_url="fake_icon_url", rp_id="fake_rp_id")
    ]
    assert assertion_cls.calls == [
        pretend.call(
            not_a_real_user,
            not_a_real_assertion,
            webauthn._webauthn_b64encode("not_a_real_challenge".encode()).decode(),
            "fake_origin",
            allow_credentials=["not_a_real_credential"],
        )
    ]
    assert resp == ("not_a_real_credential", 1234)


def test_verify_assertion_response_failure(monkeypatch):
    assertion_obj = pretend.stub(
        verify=pretend.raiser(pywebauthn.webauthn.AuthenticationRejectedException)
    )
    assertion_cls = pretend.call_recorder(lambda *a, **kw: assertion_obj)
    monkeypatch.setattr(pywebauthn, "WebAuthnAssertionResponse", assertion_cls)

    get_webauthn_users = pretend.call_recorder(
        lambda *a, **kw: [pretend.stub(credential_id=pretend.stub())]
    )
    monkeypatch.setattr(webauthn, "_get_webauthn_users", get_webauthn_users)

    with pytest.raises(webauthn.AuthenticationRejectedException):
        webauthn.verify_assertion_response(
            pretend.stub(),
            challenge="not_a_real_challenge",
            user=pretend.stub(),
            origin="fake_origin",
            icon_url="fake_icon_url",
            rp_id="fake_rp_id",
        )
