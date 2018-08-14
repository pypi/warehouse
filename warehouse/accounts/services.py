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
import hashlib
import hmac
import logging
import posixpath
import urllib.parse
import uuid

import requests

from passlib.context import CryptContext
from sqlalchemy.orm.exc import NoResultFound
from zope.interface import implementer

from warehouse.accounts.interfaces import (
    IUserService,
    ITokenService,
    IPasswordBreachedService,
    TokenExpired,
    TokenInvalid,
    TokenMissing,
    TooManyFailedLogins,
)
from warehouse.accounts.models import Email, User
from warehouse.metrics import IMetricsService
from warehouse.rate_limiting import IRateLimiter, DummyRateLimiter
from warehouse.utils.crypto import BadData, SignatureExpired, URLSafeTimedSerializer


logger = logging.getLogger(__name__)

PASSWORD_FIELD = "password"


@implementer(IUserService)
class DatabaseUserService:
    def __init__(self, session, *, ratelimiters=None, metrics):
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
        self._metrics = metrics

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
    def get_user_by_email(self, email):
        user_id = self.find_userid_by_email(email)
        return None if user_id is None else self.get_user(user_id)

    @functools.lru_cache()
    def find_userid(self, username):
        try:
            user = self.db.query(User.id).filter(User.username == username).one()
        except NoResultFound:
            return

        return user.id

    @functools.lru_cache()
    def find_userid_by_email(self, email):
        try:
            # flake8: noqa
            user_id = (self.db.query(Email.user_id).filter(Email.email == email).one())[
                0
            ]
        except NoResultFound:
            return

        return user_id

    def check_password(self, userid, password, *, tags=None):
        tags = tags if tags is not None else []

        self._metrics.increment("warehouse.authentication.start", tags=tags)

        # The very first thing we want to do is check to see if we've hit our
        # global rate limit or not, assuming that we've been configured with a
        # global rate limiter anyways.
        if not self.ratelimiters["global"].test():
            logger.warning("Global failed login threshold reached.")
            self._metrics.increment(
                "warehouse.authentication.ratelimited",
                tags=tags + ["ratelimiter:global"],
            )
            raise TooManyFailedLogins(resets_in=self.ratelimiters["global"].resets_in())

        user = self.get_user(userid)
        if user is not None:
            # Now, check to make sure that we haven't hitten a rate limit on a
            # per user basis.
            if not self.ratelimiters["user"].test(user.id):
                self._metrics.increment(
                    "warehouse.authentication.ratelimited",
                    tags=tags + ["ratelimiter:user"],
                )
                raise TooManyFailedLogins(
                    resets_in=self.ratelimiters["user"].resets_in(user.id)
                )

            # Actually check our hash, optionally getting a new hash for it if
            # we should upgrade our saved hashed.
            ok, new_hash = self.hasher.verify_and_update(password, user.password)

            # First, check to see if the password that we were given was OK.
            if ok:
                # Then, if the password was OK check to see if we've been given
                # a new password hash from the hasher, if so we'll want to save
                # that hash.
                if new_hash:
                    user.password = new_hash

                self._metrics.increment("warehouse.authentication.ok", tags=tags)

                return True
            else:
                self._metrics.increment(
                    "warehouse.authentication.failure",
                    tags=tags + ["failure_reason:password"],
                )
        else:
            self._metrics.increment(
                "warehouse.authentication.failure", tags=tags + ["failure_reason:user"]
            )

        # If we've gotten here, then we'll want to record a failed login in our
        # rate limiting before returning False to indicate a failed password
        # verification.
        if user is not None:
            self.ratelimiters["user"].hit(user.id)
        self.ratelimiters["global"].hit()

        return False

    def create_user(
        self,
        username,
        name,
        password,
        is_active=False,
        is_staff=False,
        is_superuser=False,
    ):

        user = User(
            username=username,
            name=name,
            password=self.hasher.hash(password),
            is_active=is_active,
            is_staff=is_staff,
            is_superuser=is_superuser,
        )
        self.db.add(user)
        self.db.flush()  # flush the db now so user.id is available

        return user

    def add_email(self, user_id, email_address, primary=None, verified=False):
        user = self.get_user(user_id)

        # If primary is None, then we're going to auto detect whether this should be the
        # primary address or not. The basic rule is that if the user doesn't already
        # have a primary address, then the address we're adding now is going to be
        # set to their primary.
        if primary is None:
            primary = True if user.primary_email is None else False

        email = Email(
            email=email_address, user=user, primary=primary, verified=verified
        )
        self.db.add(email)
        self.db.flush()  # flush the db now so email.id is available

        return email

    def update_user(self, user_id, **changes):
        user = self.get_user(user_id)
        for attr, value in changes.items():
            if attr == PASSWORD_FIELD:
                value = self.hasher.hash(value)
            setattr(user, attr, value)

        # If we've given the user a new password, then we also want to unset the
        # reason for disable... because a new password means no more disabled
        # user.
        if PASSWORD_FIELD in changes:
            user.disabled_for = None

        return user

    def disable_password(self, user_id, reason=None):
        user = self.get_user(user_id)
        user.password = self.hasher.disable()
        user.disabled_for = reason

    def is_disabled(self, user_id):
        user = self.get_user(user_id)

        # User is not disabled.
        if self.hasher.is_enabled(user.password):
            return (False, None)
        # User is disabled.
        else:
            return (True, user.disabled_for)


@implementer(ITokenService)
class TokenService:
    def __init__(self, secret, salt, max_age):
        self.serializer = URLSafeTimedSerializer(secret, salt=salt)
        self.max_age = max_age

    def dumps(self, data):
        return self.serializer.dumps({key: str(value) for key, value in data.items()})

    def loads(self, token):
        if not token:
            raise TokenMissing

        try:
            data = self.serializer.loads(token, max_age=self.max_age)
        except SignatureExpired:
            raise TokenExpired
        except BadData:  #  Catch all other exceptions
            raise TokenInvalid

        return data


def database_login_factory(context, request):
    return DatabaseUserService(
        request.db,
        metrics=request.find_service(IMetricsService, context=None),
        ratelimiters={
            "global": request.find_service(
                IRateLimiter, name="global.login", context=None
            ),
            "user": request.find_service(IRateLimiter, name="user.login", context=None),
        },
    )


class TokenServiceFactory:
    def __init__(self, name, service_class=TokenService):
        self.name = name
        self.service_class = service_class

    def __call__(self, context, request):
        secret = request.registry.settings[f"token.{self.name}.secret"]
        salt = self.name  # Use the service name as the unique salt
        max_age = request.registry.settings.get(
            f"token.{self.name}.max_age",
            request.registry.settings["token.default.max_age"],
        )

        return self.service_class(secret, salt, max_age)

    def __eq__(self, other):
        if not isinstance(other, TokenServiceFactory):
            return NotImplemented

        return (self.name, self.service_class) == (other.name, other.service_class)


@implementer(IPasswordBreachedService)
class HaveIBeenPwnedPasswordBreachedService:

    _failure_message_preamble = (
        "This password appears in a breach or has been compromised and cannot be used."
    )

    def __init__(
        self,
        *,
        session,
        metrics,
        api_base="https://api.pwnedpasswords.com",
        help_url=None,
    ):
        self._http = session
        self._api_base = api_base
        self._metrics = metrics
        self._help_url = help_url

    @classmethod
    def create_service(cls, context, request):
        return cls(
            session=request.http,
            metrics=request.find_service(IMetricsService, context=None),
            help_url=request.help_url(_anchor="compromised-password"),
        )

    @property
    def failure_message(self):
        message = self._failure_message_preamble
        if self._help_url:
            message += (
                f' See <a href="{self._help_url}">this FAQ entry</a> for more '
                "information."
            )
        return message

    @property
    def failure_message_plain(self):
        message = self._failure_message_preamble
        if self._help_url:
            message += f" See the FAQ entry at {self._help_url} for more information."
        return message

    def _metrics_increment(self, *args, **kwargs):
        self._metrics.increment(*args, **kwargs)

    def _get_url(self, prefix):
        return urllib.parse.urljoin(self._api_base, posixpath.join("/range/", prefix))

    def check_password(self, password, *, tags=None):
        # The HIBP API impements a k-Anonymity scheme, by which you can take a given
        # password, hash it using sha1, and then send only the first 5 characters of the
        # hex encoded digest. This avoids leaking data to the HIBP API, because without
        # the rest of the hash, the HIBP service cannot even begin to brute force or do
        # a reverse lookup to determine what password has just been sent to it. For More
        # information see:
        #       https://www.troyhunt.com/ive-just-launched-pwned-passwords-version-2/

        self._metrics_increment("warehouse.compromised_password_check.start", tags=tags)

        # To work with the HIBP API, we need the sha1 of the UTF8 encoded passsword.
        hashed_password = hashlib.sha1(password.encode("utf8")).hexdigest().lower()

        # Fetch the passwords from the HIBP data set.
        try:
            resp = self._http.get(self._get_url(hashed_password[:5]))
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Error contacting HaveIBeenPwned: %r", exc)
            self._metrics_increment(
                "warehouse.compromised_password_check.error", tags=tags
            )

            # If we've failed to contact the HIBP service for some reason, we're going
            # to "fail open" and allow the password. That's a better option then just
            # hard failing whatever the user is attempting to do.
            return False

        # The dataset that comes back from HIBP looks like:
        #
        #   0018A45C4D1DEF81644B54AB7F969B88D65:1
        #   00D4F6E8FA6EECAD2A3AA415EEC418D38EC:2
        #   011053FD0102E94D6AE2F8B83D76FAF94F6:1
        #   012A7CA357541F0AC487871FEEC1891C49C:2
        #   0136E006E24E7D152139815FB0FC6A50B15:2
        #   ...
        #
        # THat is, it is a line delimited textual data, where each line is a hash, a
        # colon, and then the number of times that password has appeared in a breach.
        # For our uses, we're going to consider any password that has ever appeared in
        # a breach to be insecure, even if only once.
        for line in resp.text.splitlines():
            possible, _ = line.split(":")
            if hashed_password[5:] == possible.lower():
                self._metrics_increment(
                    "warehouse.compromised_password_check.compromised", tags=tags
                )
                return True

        # If we made it to this point, then the password is safe.
        self._metrics_increment("warehouse.compromised_password_check.ok", tags=tags)
        return False


@implementer(IPasswordBreachedService)
class NullPasswordBreachedService:
    failure_message = "This password appears in a breach."
    failure_message_plain = "This password appears in a breach."

    @classmethod
    def create_service(cls, context, request):
        return cls()

    def check_password(self, password, *, tags=None):
        # This service allows *every* password as a non-breached password. It will never
        # tell a user their password isn't good enough.
        return False
