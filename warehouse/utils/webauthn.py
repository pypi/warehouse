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


def _generate_challenge():
    """
    Returns a random challenge suitable for use within
    Webauthn's credential and configuration option objects.

    See: https://w3c.github.io/webauthn/#cryptographic-challenges
    """
    # NOTE: Webauthn recommends at least 16 bytes of entropy,
    # we go with 32 because it doesn't cost us anything.
    return base64.b64encode(os.urandom(32)).decode()


def _get_webauthn_user(user):
    """
    Returns a webauthn.WebAuthnUser instance corresponding
    to the given user model, with properties suitable for
    usage within the webauthn API.
    """
    return pywebauthn.WebAuthnUser(
        user.id,
        user.username,
        user.name,
        None,  # TODO(ww): icon_url
        user.webauthn.credential_id,
        user.webauthn.public_key,
        user.webauthn.sign_count,
        None,  # TODO(ww): rp_id
    )


def get_credential_options(user):
    """
    Returns a dictionary of options for credential creation
    on the client side.
    """
    options = pywebauthn.WebAuthnMakeCredentialOptions(
        _generate_challenge(),
        None,  # TODO(ww): rp_name
        None,  # TODO(ww): rp_id
        user.id,
        user.username,
        user.name,
        None,  # TODO(ww): icon_url
    )

    return options.registration_dict()


def get_assertion_options(user):
    """
    Returns a dictionary of options for assertion retrieval
    on the client side.
    """
    options = pywebauthn.WebAuthnAssertionOptions(
        _get_webauthn_user(user),
        _generate_challenge(),
    )

    return options.assertion_dict()


def verify_registration_response(response, challenge):
    """
    Validates the challenge and attestation information
    sent from the client during device registration.

    Returns a webauthn.WebAuthnCredential on success.
    Raises webauthn.RegistrationRejectedException on failire.
    """
    response = pywebauthn.WebAuthnRegistrationResponse(
        None,  # TODO(ww): rp_id
        None,  # TODO(ww): origin
        response,
        challenge,
    )

    return response.verify()


def verify_assertion_response(response, challenge, user):
    """
    Validates the challenge and assertion information
    sent from the client during authentication.

    Returns an updated signage count on success.
    Raises webauthn.AuthenticationRejectedException on failure.
    """
    response = pywebauthn.WebAuthnAssertionResponse(
        _get_webauthn_user(user),
        response,
        challenge,
        None,  # TODO(ww): origin
    )

    return response.verify()
