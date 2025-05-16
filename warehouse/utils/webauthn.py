# SPDX-License-Identifier: Apache-2.0

import base64
import json

import webauthn as pywebauthn

from webauthn.helpers import (
    base64url_to_bytes,
    generate_challenge,
    parse_authentication_credential_json,
    parse_registration_credential_json,
)
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidAuthenticatorDataStructure,
    InvalidRegistrationResponse,
    UnsupportedPublicKeyType,
)
from webauthn.helpers.options_to_json import options_to_json
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
)


class AuthenticationRejectedError(Exception):
    pass


class RegistrationRejectedError(Exception):
    pass


def _get_webauthn_user_public_key_credential_descriptors(user, *, rp_id):
    """
    Returns a webauthn.WebAuthnUser instance corresponding
    to the given user model, with properties suitable for
    usage within the webauthn API.
    """
    return [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(credential.credential_id))
        for credential in user.webauthn
    ]


def _get_webauthn_user_public_keys(user, *, rp_id):
    return [
        (
            base64url_to_bytes(credential.public_key),
            credential.sign_count,
        )
        for credential in user.webauthn
    ]


def _webauthn_b64encode(source):
    return base64.urlsafe_b64encode(source).rstrip(b"=")


def generate_webauthn_challenge():
    """
    Returns a random challenge suitable for use within
    Webauthn's credential and configuration option objects.

    See: https://w3c.github.io/webauthn/#cryptographic-challenges
    """
    return generate_challenge()


def get_credential_options(user, *, challenge, rp_name, rp_id):
    """
    Returns a dictionary of options for credential creation
    on the client side.
    """
    _authenticator_selection = AuthenticatorSelectionCriteria()
    _authenticator_selection.user_verification = UserVerificationRequirement.DISCOURAGED
    options = pywebauthn.generate_registration_options(
        rp_id=rp_id,
        rp_name=rp_name,
        user_id=str(user.id).encode(),
        user_name=user.username,
        user_display_name=user.name or user.username,
        challenge=challenge,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=_authenticator_selection,
    )
    return json.loads(options_to_json(options))


def get_assertion_options(user, *, challenge, rp_id):
    """
    Returns a dictionary of options for assertion retrieval
    on the client side.
    """
    options = pywebauthn.generate_authentication_options(
        rp_id=rp_id,
        challenge=challenge,
        allow_credentials=_get_webauthn_user_public_key_credential_descriptors(
            user, rp_id=rp_id
        ),
        user_verification=UserVerificationRequirement.DISCOURAGED,
    )
    return json.loads(options_to_json(options))


def verify_registration_response(response, challenge, *, rp_id, origin):
    """
    Validates the challenge and attestation information
    sent from the client during device registration.

    Returns a WebAuthnCredential on success.
    Raises RegistrationRejectedError on failire.
    """
    # NOTE: We re-encode the challenge below, because our
    # response's clientData.challenge is encoded twice:
    # first for the entire clientData payload, and then again
    # for the individual challenge.
    encoded_challenge = _webauthn_b64encode(challenge)
    try:
        _credential = parse_registration_credential_json(response.decode())
        return pywebauthn.verify_registration_response(
            credential=_credential,
            expected_challenge=encoded_challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=False,
        )
    except (
        InvalidAuthenticatorDataStructure,
        InvalidRegistrationResponse,
        UnsupportedPublicKeyType,
    ) as e:
        raise RegistrationRejectedError(str(e))


def verify_assertion_response(assertion, *, challenge, user, origin, rp_id):
    """
    Validates the challenge and assertion information
    sent from the client during authentication.

    Returns an updated signage count on success.
    Raises AuthenticationRejectedError on failure.
    """
    # NOTE: We re-encode the challenge below, because our
    # response's clientData.challenge is encoded twice:
    # first for the entire clientData payload, and then again
    # for the individual challenge.
    encoded_challenge = _webauthn_b64encode(challenge)
    webauthn_user_public_keys = _get_webauthn_user_public_keys(user, rp_id=rp_id)

    for public_key, current_sign_count in webauthn_user_public_keys:
        try:
            _credential = parse_authentication_credential_json(assertion.decode())
            return pywebauthn.verify_authentication_response(
                credential=_credential,
                expected_challenge=encoded_challenge,
                expected_rp_id=rp_id,
                expected_origin=origin,
                credential_public_key=public_key,
                credential_current_sign_count=current_sign_count,
                require_user_verification=False,
            )
        except InvalidAuthenticationResponse:
            pass

    # If we exit the loop, then we've failed to verify the assertion against
    # any of the user's WebAuthn credentials. Fail.
    raise AuthenticationRejectedError("Invalid WebAuthn credential")
