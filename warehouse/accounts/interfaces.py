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

from zope.interface import Attribute, Interface


class RateLimiterException(Exception):
    def __init__(self, *args, resets_in, **kwargs):
        self.resets_in = resets_in

        return super().__init__(*args, **kwargs)


class TooManyFailedLogins(RateLimiterException):
    pass


class TooManyEmailsAdded(RateLimiterException):
    pass


class TokenException(Exception):
    pass


class TokenExpired(TokenException):
    pass


class TokenInvalid(TokenException):
    pass


class TokenMissing(TokenException):
    pass


class IUserService(Interface):
    def get_user(user_id):
        """
        Return the user object that represents the given userid, or None if
        there is no user for that ID.
        """

    def get_user_by_username(username):
        """
        Return the user object corresponding with the given username, or None
        if there is no user with that username.
        """

    def get_user_by_email(email):
        """
        Return the user object corresponding with the given email, or None
        if there is no user with that email.
        """

    def find_userid(username):
        """
        Find the unique user identifier for the given username or None if there
        is no user with the given username.
        """

    def check_password(user_id, password, *, tags=None):
        """
        Returns a boolean representing whether the given password is valid for
        the given userid.

        May have an optional list of tags, which allows identifying the purpose of
        checking the password.
        """

    def create_user(username, name, password):
        """
        Accepts a user object, and attempts to create a user with those
        attributes.

        A UserAlreadyExists Exception is raised if the user already exists.
        """

    def add_email(
        user_id, email_address, ip_address, primary=False, verified=False, public=False
    ):
        """
        Adds an email for the provided user_id
        """

    def update_user(user_id, **changes):
        """
        Updates the user object
        """

    def disable_password(user_id, reason=None):
        """
        Disables the given user's password, preventing further login until the user
        resets their password. If a reason was given, this will be persisted and reset
        when the user is re-enabled.
        """

    def is_disabled(user_id):
        """
        Checks if a user has been disabled, and returns a tuple of
        (IsDisabled: bool, Reason: Optional[DisableReason])
        """

    def has_two_factor(user_id):
        """
        Returns True if the user has any form of two factor
        authentication and is allowed to use it.
        """

    def has_totp(user_id):
        """
        Returns True if the user has a TOTP device provisioned.
        """

    def has_webauthn(user_id):
        """
        Returns True if the user has a security key provisioned.
        """

    def has_recovery_codes(user_id):
        """
        Returns True if the user has at least one valid recovery code.
        """

    def get_recovery_codes(user_id):
        """
        Returns RecoveryCode objects associated with the user.
        """

    def get_totp_secret(user_id):
        """
        Returns the user's TOTP secret as bytes.

        If the user doesn't have a TOTP secret or is not
        allowed to use a second factor, returns None.
        """

    def check_totp_value(user_id, totp_value, *, tags=None):
        """
        Returns True if the given TOTP code is valid.
        """

    def add_webauthn(user_id, **kwargs):
        """
        Adds a WebAuthn credential to the given user.

        Returns None if the user already has this credential.
        """

    def get_webauthn_credential_options(user_id, *, challenge, rp_name, rp_id):
        """
        Returns a dictionary of credential options suitable for beginning the WebAuthn
        provisioning process for the given user.
        """

    def get_webauthn_assertion_options(user_id, *, challenge, rp_id):
        """
        Returns a dictionary of assertion options suitable for beginning the WebAuthn
        authentication process for the given user.
        """

    def verify_webauthn_credential(credential, *, challenge, rp_id, origin):
        """
        Checks whether the given credential is valid, i.e. suitable for generating
        assertions during authentication.

        Returns the validated credential on success, raises
        webauthn.RegistrationRejectedException on failure.
        """

    def verify_webauthn_assertion(user_id, assertion, *, challenge, origin, rp_id):
        """
        Checks whether the given assertion was produced by the given user's WebAuthn
        device.

        Returns the updated signage count on success, raises
        webauthn.AuthenticationRejectedException on failure.
        """

    def get_webauthn_by_label(user_id, label):
        """
        Returns a WebAuthn credential for the given user by its label,
        or None if no credential for the user has this label.
        """

    def get_webauthn_by_credential_id(user_id, credential_id):
        """
        Returns a WebAuthn credential for the given user by its credential ID,
        or None of the user doesn't have a credential with this ID.
        """

    def record_event(user_id, *, tag, ip_address, additional=None):
        """
        Creates a new UserEvent for the given user with the given
        tag, IP address, and additional metadata.

        Returns the event.
        """

    def generate_recovery_codes(user_id):
        """
        Generates RecoveryCode objects for the given user.

        Returns a list of plain-text codes.
        """

    def check_recovery_code(user_id, code):
        """
        Checks if supplied code matches a valid hashed recovery code for the given user.

        Returns True if supplied recovery code is valid, and destroys stored code.
        """


class ITokenService(Interface):
    def dumps(data):
        """
        Generates a unique token based on the data provided
        """

    def loads(token):
        """
        Gets the data corresponding to the token provided
        """


class IPasswordBreachedService(Interface):
    failure_message = Attribute("The message to describe the failure that occurred")
    failure_message_plain = Attribute(
        "The message to describe the failure that occurred in plain text"
    )

    def check_password(password, *, tags=None):
        """
        Returns a boolean indicating if the given password has been involved in a breach
        or is otherwise insecure.

        May have an optional list of tags, which allows identifying the purpose of
        checking the password.
        """
