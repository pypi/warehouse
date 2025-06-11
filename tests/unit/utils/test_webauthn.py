# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest
import webauthn as pywebauthn

from webauthn.authentication.verify_authentication_response import (
    VerifiedAuthentication,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AttestationFormat,
    AuthenticationCredential,
    AuthenticatorAssertionResponse,
    AuthenticatorAttestationResponse,
    PublicKeyCredentialType,
    RegistrationCredential,
)
from webauthn.registration.verify_registration_response import VerifiedRegistration

import warehouse.utils.webauthn as webauthn


def test_generate_webauthn_challenge():
    challenge = webauthn.generate_webauthn_challenge()

    assert isinstance(challenge, bytes)
    assert challenge == base64url_to_bytes(bytes_to_base64url(challenge))


def test_verify_registration_response(monkeypatch):
    fake_verified_registration = VerifiedRegistration(
        credential_id=b"foo",
        credential_public_key=b"bar",
        sign_count=0,
        aaguid="wutang",
        fmt=AttestationFormat.NONE,
        credential_type=PublicKeyCredentialType.PUBLIC_KEY,
        user_verified=False,
        attestation_object=b"foobar",
        credential_device_type="single_device",
        credential_backed_up=False,
    )
    mock_verify_registration_response = pretend.call_recorder(
        lambda *a, **kw: fake_verified_registration
    )
    monkeypatch.setattr(
        pywebauthn, "verify_registration_response", mock_verify_registration_response
    )

    resp = webauthn.verify_registration_response(
        (
            b'{"id": "foo", "rawId": "foo", "response": '
            b'{"attestationObject": "foo", "clientDataJSON": "bar"},'
            b'"type": "public-key"}'
        ),
        b"not_a_real_challenge",
        rp_id="fake_rp_id",
        origin="fake_origin",
    )

    assert mock_verify_registration_response.calls == [
        pretend.call(
            credential=RegistrationCredential(
                id="foo",
                raw_id=b"~\x8a",
                response=AuthenticatorAttestationResponse(
                    client_data_json=b"m\xaa", attestation_object=b"~\x8a"
                ),
                type=PublicKeyCredentialType.PUBLIC_KEY,
            ),
            expected_challenge=bytes_to_base64url(b"not_a_real_challenge").encode(),
            expected_rp_id="fake_rp_id",
            expected_origin="fake_origin",
            require_user_verification=False,
        )
    ]
    assert resp == fake_verified_registration


def test_verify_registration_response_failure(monkeypatch):
    monkeypatch.setattr(
        pywebauthn,
        "verify_registration_response",
        pretend.raiser(pywebauthn.helpers.exceptions.InvalidRegistrationResponse),
    )

    with pytest.raises(webauthn.RegistrationRejectedError):
        webauthn.verify_registration_response(
            (
                b'{"id": "foo", "rawId": "foo", "response": '
                b'{"attestationObject": "foo", "clientDataJSON": "bar"}, '
                b'"type": "public-key"}'
            ),
            b"not_a_real_challenge",
            rp_id="fake_rp_id",
            origin="fake_origin",
        )


def test_verify_assertion_response(monkeypatch):
    fake_verified_authentication = VerifiedAuthentication(
        credential_id=b"a credential id",
        new_sign_count=69,
        credential_device_type="single_device",
        credential_backed_up=False,
        user_verified=False,
    )
    mock_verify_authentication_response = pretend.call_recorder(
        lambda *a, **kw: fake_verified_authentication
    )
    monkeypatch.setattr(
        pywebauthn,
        "verify_authentication_response",
        mock_verify_authentication_response,
    )

    not_a_real_user = pretend.stub(
        webauthn=[
            pretend.stub(
                public_key=bytes_to_base64url(b"fake public key"), sign_count=68
            )
        ]
    )
    resp = webauthn.verify_assertion_response(
        (
            b'{"id": "foo", "rawId": "foo", "response": '
            b'{"authenticatorData": "foo", "clientDataJSON": "bar", '
            b'"signature": "wutang"}, '
            b'"type": "public-key"}'
        ),
        challenge=b"not_a_real_challenge",
        user=not_a_real_user,
        origin="fake_origin",
        rp_id="fake_rp_id",
    )

    assert mock_verify_authentication_response.calls == [
        pretend.call(
            credential=AuthenticationCredential(
                id="foo",
                raw_id=b"~\x8a",
                response=AuthenticatorAssertionResponse(
                    client_data_json=b"m\xaa",
                    authenticator_data=b"~\x8a",
                    signature=b"\xc2\xebZ\x9e",
                    user_handle=None,
                ),
                type=PublicKeyCredentialType.PUBLIC_KEY,
            ),
            expected_challenge=b"bm90X2FfcmVhbF9jaGFsbGVuZ2U",
            expected_rp_id="fake_rp_id",
            expected_origin="fake_origin",
            credential_public_key=b"fake public key",
            credential_current_sign_count=68,
            require_user_verification=False,
        )
    ]
    assert resp == fake_verified_authentication


def test_verify_assertion_response_failure(monkeypatch):
    monkeypatch.setattr(
        pywebauthn,
        "verify_authentication_response",
        pretend.raiser(pywebauthn.helpers.exceptions.InvalidAuthenticationResponse),
    )

    get_webauthn_users = pretend.call_recorder(
        lambda *a, **kw: [(b"not a public key", 0)]
    )
    monkeypatch.setattr(webauthn, "_get_webauthn_user_public_keys", get_webauthn_users)

    with pytest.raises(webauthn.AuthenticationRejectedError):
        webauthn.verify_assertion_response(
            (
                b'{"id": "foo", "rawId": "foo", "response": '
                b'{"authenticatorData": "foo", "clientDataJSON": "bar", '
                b'"signature": "wutang"}, '
                b'"type": "public-key"}'
            ),
            challenge=b"not_a_real_challenge",
            user=pretend.stub(),
            origin="fake_origin",
            rp_id="fake_rp_id",
        )
