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

from zope.interface import Interface


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

    def get_user(userid):
        """
        Return the user object that represents the given userid, or None if
        there is no user for that ID.
        """

    def get_user_by_username(username):
        """
        Return the user object corresponding with the given username, or None
        if there is no user with that username.
        """

    def find_userid(username):
        """
        Find the unique user identifier for the given username or None if there
        is no user with the given username.
        """

    def check_password(userid, password):
        """
        Returns a boolean representing whether the given password is valid for
        the given userid.
        """

    def create_user(username, name, password, email,
                    is_active=False, is_staff=False, is_superuser=False):
        """
        Accepts a user object, and attempts to create a user with those
        attributes.

        A UserAlreadyExists Exception is raised if the user already exists.
        """

    def update_user(user_id, **changes):
        """
        Updates the user object
        """

    def verify_email(user_id, email_address):
        """
        verifies the user
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
