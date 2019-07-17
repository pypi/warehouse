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
import os

import webauthn as pywebauthn

from webauthn.webauthn import (
    AuthenticationRejectedException as _AuthenticationRejectedException,
    RegistrationRejectedException as _RegistrationRejectedException,
)


class AuthenticationRejectedException(Exception):
    pass


class RegistrationRejectedException(Exception):
    pass


WebAuthnCredential = pywebauthn.WebAuthnCredential


def _get_webauthn_users(user, *, icon_url, rp_id):
    """
    Returns a webauthn.WebAuthnUser instance corresponding
    to the given user model, with properties suitable for
    usage within the webauthn API.
    """
    return [
        pywebauthn.WebAuthnUser(
            str(user.id),
            user.username,
            user.name,
            icon_url,
            credential.credential_id,
            credential.public_key,
            credential.sign_count,
            rp_id,
        )
        for credential in user.webauthn
    ]


def _webauthn_b64decode(encoded):
    padding = "=" * (len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


def _webauthn_b64encode(source):
    return base64.urlsafe_b64encode(source).rstrip(b"=")


def generate_webauthn_challenge():
    """
    Returns a random challenge suitable for use within
    Webauthn's credential and configuration option objects.

    See: https://w3c.github.io/webauthn/#cryptographic-challenges
    """
    # NOTE: Webauthn recommends at least 16 bytes of entropy,
    # we go with 32 because it doesn't cost us anything.
    return _webauthn_b64encode(os.urandom(32)).decode()


def get_credential_options(user, *, challenge, rp_name, rp_id, icon_url):
    """
    Returns a dictionary of options for credential creation
    on the client side.
    """
    options = pywebauthn.WebAuthnMakeCredentialOptions(
        challenge, rp_name, rp_id, str(user.id), user.username, user.name, icon_url
    )

    return options.registration_dict


def get_assertion_options(user, *, challenge, icon_url, rp_id):
    """
    Returns a dictionary of options for assertion retrieval
    on the client side.
    """
    options = pywebauthn.WebAuthnAssertionOptions(
        _get_webauthn_users(user, icon_url=icon_url, rp_id=rp_id), challenge
    )

    return options.assertion_dict


def verify_registration_response(response, challenge, *, rp_id, origin):
    """
    Validates the challenge and attestation information
    sent from the client during device registration.

    Returns a WebAuthnCredential on success.
    Raises RegistrationRejectedException on failire.
    """
    # NOTE: We re-encode the challenge below, because our
    # response's clientData.challenge is encoded twice:
    # first for the entire clientData payload, and then again
    # for the individual challenge.
    encoded_challenge = _webauthn_b64encode(challenge.encode()).decode()
    response = pywebauthn.WebAuthnRegistrationResponse(
        rp_id, origin, response, encoded_challenge, self_attestation_permitted=True
    )
    try:
        return response.verify()
    except _RegistrationRejectedException as e:
        raise RegistrationRejectedException(str(e))


def verify_assertion_response(assertion, *, challenge, user, origin, icon_url, rp_id):
    """
    Validates the challenge and assertion information
    sent from the client during authentication.

    Returns an updated signage count on success.
    Raises AuthenticationRejectedException on failure.
    """
    webauthn_users = _get_webauthn_users(user, icon_url=icon_url, rp_id=rp_id)
    cred_ids = [cred.credential_id for cred in webauthn_users]
    encoded_challenge = _webauthn_b64encode(challenge.encode()).decode()

    for webauthn_user in webauthn_users:
        response = pywebauthn.WebAuthnAssertionResponse(
            webauthn_user,
            assertion,
            encoded_challenge,
            origin,
            allow_credentials=cred_ids,
        )
        try:
            return (webauthn_user.credential_id, response.verify())
        except _AuthenticationRejectedException:
            pass

    # If we exit the loop, then we've failed to verify the assertion against
    # any of the user's WebAuthn credentials. Fail.
    raise AuthenticationRejectedException("Invalid WebAuthn credential")
