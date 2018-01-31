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

import collections
import functools
import hmac
import logging
import uuid

from passlib.context import CryptContext
from sqlalchemy.orm.exc import NoResultFound
from zope.interface import implementer

from warehouse.accounts.interfaces import (
    IUserService, ITokenService, TokenExpired, TokenInvalid, TokenMissing,
    TooManyFailedLogins,
)
from warehouse.accounts.models import Email, User
from warehouse.rate_limiting import IRateLimiter, DummyRateLimiter
from warehouse.utils.crypto import (
    BadData, SignatureExpired, URLSafeTimedSerializer,
)


logger = logging.getLogger(__name__)

PASSWORD_FIELD = "password"


@implementer(IUserService)
class DatabaseUserService:

    def __init__(self, session, ratelimiters=None):
        if ratelimiters is None:
            ratelimiters = {}
        ratelimiters = collections.defaultdict(DummyRateLimiter, ratelimiters)

        self.db = session
        self.ratelimiters = ratelimiters
        self.hasher = CryptContext(
            schemes=[
                "argon2",
                "bcrypt_sha256",
                "bcrypt",
                "django_bcrypt",
                "unix_disabled",
            ],
            deprecated=["auto"],
            truncate_error=True,

            # Argon 2 Configuration
            argon2__memory_cost=1024,
            argon2__parallelism=6,
            argon2__time_cost=6,
        )


    @functools.lru_cache()
    def get_user(self, userid):
        # TODO: We probably don't actually want to just return the database
        #       object here.
        # TODO: We need some sort of Anonymous User.
        return self.db.query(User).get(userid)

    @functools.lru_cache()
    def get_user_by_username(self, username):
        user_id = self.find_userid(username)
        return None if user_id is None else self.get_user(user_id)

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
        # The very first thing we want to do is check to see if we've hit our
        # global rate limit or not, assuming that we've been configured with a
        # global rate limiter anyways.
        if not self.ratelimiters["global"].test():
            logger.warning("Global failed login threshold reached.")
            raise TooManyFailedLogins(
                resets_in=self.ratelimiters["global"].resets_in(),
            )

        user = self.get_user(userid)
        if user is not None:
            # Now, check to make sure that we haven't hitten a rate limit on a
            # per user basis.
            if not self.ratelimiters["user"].test(user.id):
                raise TooManyFailedLogins(
                    resets_in=self.ratelimiters["user"].resets_in(user.id),
                )

            # Actually check our hash, optionally getting a new hash for it if
            # we should upgrade our saved hashed.
            ok, new_hash = self.hasher.verify_and_update(
                password,
                user.password,
            )

            # First, check to see if the password that we were given was OK.
            if ok:
                # Then, if the password was OK check to see if we've been given
                # a new password hash from the hasher, if so we'll want to save
                # that hash.
                if new_hash:
                    user.password = new_hash

                return True

        # If we've gotten here, then we'll want to record a failed login in our
        # rate limiting before returning False to indicate a failed password
        # verification.
        if user is not None:
            self.ratelimiters["user"].hit(user.id)
        self.ratelimiters["global"].hit()

        return False

    def create_user(self, username, name, password, email,
                    is_active=False, is_staff=False, is_superuser=False):

        user = User(username=username,
                    name=name,
                    password=self.hasher.hash(password),
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
            if attr == PASSWORD_FIELD:
                value = self.hasher.hash(value)
            setattr(user, attr, value)
        return user

    def verify_email(self, user_id, email_address):
        user = self.get_user(user_id)
        for email in user.emails:
            if email.email == email_address:
                email.verified = True


@implementer(ITokenService)
class TokenService:
    def __init__(self, secret, salt, max_age):
        self.serializer = URLSafeTimedSerializer(secret, salt=salt)
        self.max_age = max_age

    def dumps(self, data):
        return self.serializer.dumps({
            key: str(value)
            for key, value in data.items()
        })

    def loads(self, token):
        if not token:
            raise TokenMissing

        try:
            data = self.serializer.loads(token, max_age=self.max_age)
        except SignatureExpired:
            raise TokenExpired
        except BadData: #  Catch all other exceptions
            raise TokenInvalid

        return data


def database_login_factory(context, request):
    return DatabaseUserService(
        request.db,
        ratelimiters={
            "global": request.find_service(
                IRateLimiter,
                name="global.login",
                context=None,
            ),
            "user": request.find_service(
                IRateLimiter,
                name="user.login",
                context=None,
            ),
        },
    )


class TokenServiceFactory:

    def __init__(self, name, service_class=TokenService):
        self.name = name
        self.service_class = service_class

    def __call__(self, context, request):
        secret = request.registry.settings[f"token.{self.name}.secret"]
        salt = self.name
        max_age = request.registry.settings.get(
            f"token.{self.name}.max_age",
            request.registry.settings["token.default.max_age"],
        )

        return self.service_class(secret, salt, max_age)
