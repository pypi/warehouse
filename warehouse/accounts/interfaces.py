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


class TooManyFailedLogins(Exception):
    def __init__(self, *args, resets_in, **kwargs):
        self.resets_in = resets_in

        return super().__init__(*args, **kwargs)


class TokenExpired(Exception):
    pass


class TokenInvalid(Exception):
    pass


class TokenMissing(Exception):
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

        May have an optional list of tags, which allows identifiying the purpose of
        checking the password.
        """

    def create_user(
        username,
        name,
        password,
        is_active=False,
    ):
        """
        Accepts a user object, and attempts to create a user with those
        attributes.

        A UserAlreadyExists Exception is raised if the user already exists.
        """

    def add_email(user_id, email_address, primary=False, verified=False):
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
    failure_message = Attribute("The message to describe the failure that occured")
    failure_message_plain = Attribute(
        "The message to describe the failure that occured in plain text"
    )

    def check_password(password, *, tags=None):
        """
        Returns a boolean indicating if the given password has been involved in a breach
        or is otherwise insecure.

        May have an optional list of tags, which allows identifiying the purpose of
        checking the password.
        """
