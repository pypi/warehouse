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

import datetime
import functools

from passlib.context import CryptContext
from sqlalchemy.orm.exc import NoResultFound
from zope.interface import implementer

from warehouse.accounts.interfaces import IUserService
from warehouse.accounts.models import Email, User


@implementer(IUserService)
class DatabaseUserService:

    def __init__(self, session):
        self.db = session
        self.hasher = CryptContext(
            schemes=[
                "bcrypt_sha256",
                "bcrypt",
                "django_bcrypt",
                "unix_disabled",
            ],
            deprecated=["auto"],
        )

    @functools.lru_cache()
    def get_user(self, userid):
        # TODO: We probably don't actually want to just return the database
        #       object here.
        # TODO: We need some sort of Anonymous User.
        return self.db.query(User).get(userid)

    @functools.lru_cache()
    def find_userid(self, username):
        try:
            user = (
                self.db.query(User.id)
                    .filter(User.username == username)
                    .one()
            )
        except NoResultFound:
            return

        return user.id

    @functools.lru_cache()
    def find_userid_by_email(self, email):
        try:
            # flake8: noqa
            user_id = (
                self.db.query(Email.user_id)
                    .filter(Email.email == email)
                    .one()
            )[0]
        except NoResultFound:
            return

        return user_id

    def check_password(self, userid, password):
        user = self.get_user(userid)
        if user is None:
            return False

        # Actually check our hash, optionally getting a new hash for it if
        # we should upgrade our saved hashed.
        ok, new_hash = self.hasher.verify_and_update(password, user.password)

        # Check if the password itself was OK or not.
        if not ok:
            return False

        # If we've gotten a new password hash from the hasher, then we'll want
        # to save that hash.
        if new_hash:
            user.password = new_hash

        return True

    def create_user(self, username, name, password, email,
                    is_active=False, is_staff=False, is_superuser=False):

        user = User(username=username,
                    name=name,
                    password=self.hasher.encrypt(password),
                    is_active=is_active,
                    is_staff=is_staff,
                    is_superuser=is_superuser)
        self.db.add(user)
        email_object = Email(email=email, user=user,
                             primary=True, verified=False)
        self.db.add(email_object)
        # flush the db now so user.id is available
        self.db.flush()
        return user

    def update_user(self, user_id, **changes):
        user = self.get_user(user_id)
        for attr, value in changes.items():
            setattr(user, attr, value)
        return user

    def verify_email(self, user_id, email_address):
        user = self.get_user(user_id)
        for email in user.emails:
            if email.email == email_address:
                email.verified = True


def database_login_factory(context, request):
    return DatabaseUserService(request.db)
