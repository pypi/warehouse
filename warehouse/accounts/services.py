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
import secrets
import urllib.parse
import uuid

import requests

from passlib.context import CryptContext
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound
from zope.interface import implementer

import warehouse.utils.otp as otp
import warehouse.utils.webauthn as webauthn

from warehouse.accounts.interfaces import (
    IPasswordBreachedService,
    ITokenService,
    IUserService,
    TokenExpired,
    TokenInvalid,
    TokenMissing,
    TooManyEmailsAdded,
    TooManyFailedLogins,
)
from warehouse.accounts.models import Email, RecoveryCode, User, WebAuthn
from warehouse.metrics import IMetricsService
from warehouse.rate_limiting import DummyRateLimiter, IRateLimiter
from warehouse.utils.crypto import BadData, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)

PASSWORD_FIELD = "password"
RECOVERY_CODE_COUNT = 8


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
        return self.db.query(User).options(joinedload(User.webauthn)).get(userid)

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
        if not self.ratelimiters["global.login"].test():
            logger.warning("Global failed login threshold reached.")
            self._metrics.increment(
                "warehouse.authentication.ratelimited",
                tags=tags + ["ratelimiter:global"],
            )
            raise TooManyFailedLogins(
                resets_in=self.ratelimiters["global.login"].resets_in()
            )

        user = self.get_user(userid)
        if user is not None:
            # Now, check to make sure that we haven't hitten a rate limit on a
            # per user basis.
            if not self.ratelimiters["user.login"].test(user.id):
                self._metrics.increment(
                    "warehouse.authentication.ratelimited",
                    tags=tags + ["ratelimiter:user"],
                )
                raise TooManyFailedLogins(
                    resets_in=self.ratelimiters["user.login"].resets_in(user.id)
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
            self.ratelimiters["user.login"].hit(user.id)
        self.ratelimiters["global.login"].hit()

        return False

    def create_user(self, username, name, password):
        user = User(username=username, name=name, password=self.hasher.hash(password))
        self.db.add(user)
        self.db.flush()  # flush the db now so user.id is available

        return user

    def add_email(
        self,
        user_id,
        email_address,
        ip_address,
        primary=None,
        verified=False,
        public=False,
    ):
        # Check to make sure that we haven't hitten the rate limit for this IP
        if not self.ratelimiters["email.add"].test(ip_address):
            self._metrics.increment(
                "warehouse.email.add.ratelimited", tags=["ratelimiter:email.add"],
            )
            raise TooManyEmailsAdded(
                resets_in=self.ratelimiters["email.add"].resets_in(ip_address)
            )

        user = self.get_user(user_id)

        # If primary is None, then we're going to auto detect whether this should be the
        # primary address or not. The basic rule is that if the user doesn't already
        # have a primary address, then the address we're adding now is going to be
        # set to their primary.
        if primary is None:
            primary = True if user.primary_email is None else False

        email = Email(
            email=email_address,
            user=user,
            primary=primary,
            verified=verified,
            public=public,
        )
        self.db.add(email)
        self.db.flush()  # flush the db now so email.id is available

        self.ratelimiters["email.add"].hit(ip_address)
        self._metrics.increment("warehouse.email.add.ok")

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

    def has_two_factor(self, user_id):
        """
        Returns True if the user has any form of two factor
        authentication and is allowed to use it.
        """
        user = self.get_user(user_id)

        return user.has_two_factor

    def has_totp(self, user_id):
        """
        Returns True if the user has a TOTP device provisioned.
        """
        user = self.get_user(user_id)

        return user.totp_secret is not None

    def has_webauthn(self, user_id):
        """
        Returns True if the user has a security key provisioned.
        """
        user = self.get_user(user_id)

        return len(user.webauthn) > 0

    def has_recovery_codes(self, user_id):
        """
        Returns True if the user has generated recovery codes.
        """
        user = self.get_user(user_id)

        return user.has_recovery_codes

    def get_recovery_codes(self, user_id):
        user = self.get_user(user_id)

        return self.db.query(RecoveryCode).filter_by(user=user).all()

    def get_totp_secret(self, user_id):
        """
        Returns the user's TOTP secret as bytes.

        If the user doesn't have a TOTP, returns None.
        """
        user = self.get_user(user_id)

        return user.totp_secret

    def get_last_totp_value(self, user_id):
        """
        Returns the user's last (accepted) TOTP value.

        If the user doesn't have a TOTP or hasn't used their TOTP
        method, returns None.
        """
        user = self.get_user(user_id)

        return user.last_totp_value

    def check_totp_value(self, user_id, totp_value, *, tags=None):
        """
        Returns True if the given TOTP is valid against the user's secret.

        If the user doesn't have a TOTP secret or isn't allowed
        to use second factor methods, returns False.
        """
        tags = tags if tags is not None else []
        self._metrics.increment("warehouse.authentication.two_factor.start", tags=tags)

        # The very first thing we want to do is check to see if we've hit our
        # global rate limit or not, assuming that we've been configured with a
        # global rate limiter anyways.
        if not self.ratelimiters["global.login"].test():
            logger.warning("Global failed login threshold reached.")
            self._metrics.increment(
                "warehouse.authentication.two_factor.ratelimited",
                tags=tags + ["ratelimiter:global"],
            )
            raise TooManyFailedLogins(
                resets_in=self.ratelimiters["global.login"].resets_in()
            )

        # Now, check to make sure that we haven't hitten a rate limit on a
        # per user basis.
        if not self.ratelimiters["user.login"].test(user_id):
            self._metrics.increment(
                "warehouse.authentication.two_factor.ratelimited",
                tags=tags + ["ratelimiter:user"],
            )
            raise TooManyFailedLogins(
                resets_in=self.ratelimiters["user.login"].resets_in(user_id)
            )

        totp_secret = self.get_totp_secret(user_id)

        if totp_secret is None:
            self._metrics.increment(
                "warehouse.authentication.two_factor.failure",
                tags=tags + ["failure_reason:no_totp"],
            )
            # If we've gotten here, then we'll want to record a failed attempt in our
            # rate limiting before returning False to indicate a failed totp
            # verification.
            self.ratelimiters["user.login"].hit(user_id)
            self.ratelimiters["global.login"].hit()
            return False

        last_totp_value = self.get_last_totp_value(user_id)

        if last_totp_value is not None and totp_value == last_totp_value.encode():
            return False

        valid = otp.verify_totp(totp_secret, totp_value)

        if valid:
            self._metrics.increment("warehouse.authentication.two_factor.ok", tags=tags)
        else:
            self._metrics.increment(
                "warehouse.authentication.two_factor.failure",
                tags=tags + ["failure_reason:invalid_totp"],
            )
            # If we've gotten here, then we'll want to record a failed attempt in our
            # rate limiting before returning False to indicate a failed totp
            # verification.
            self.ratelimiters["user.login"].hit(user_id)
            self.ratelimiters["global.login"].hit()

        return valid

    def get_webauthn_credential_options(self, user_id, *, challenge, rp_name, rp_id):
        """
        Returns a dictionary of credential options suitable for beginning the WebAuthn
        provisioning process for the given user.
        """
        user = self.get_user(user_id)

        return webauthn.get_credential_options(
            user, challenge=challenge, rp_name=rp_name, rp_id=rp_id
        )

    def get_webauthn_assertion_options(self, user_id, *, challenge, rp_id):
        """
        Returns a dictionary of assertion options suitable for beginning the WebAuthn
        authentication process for the given user.
        """
        user = self.get_user(user_id)

        return webauthn.get_assertion_options(user, challenge=challenge, rp_id=rp_id)

    def verify_webauthn_credential(self, credential, *, challenge, rp_id, origin):
        """
        Checks whether the given credential is valid, i.e. suitable for generating
        assertions during authentication.

        Returns the validated credential on success, raises
        webauthn.RegistrationRejectedException on failure.
        """
        validated_credential = webauthn.verify_registration_response(
            credential, challenge=challenge, rp_id=rp_id, origin=origin
        )

        webauthn_cred = (
            self.db.query(WebAuthn)
            .filter_by(credential_id=validated_credential.credential_id.decode())
            .first()
        )

        if webauthn_cred is not None:
            raise webauthn.RegistrationRejectedException("Credential ID already in use")

        return validated_credential

    def verify_webauthn_assertion(
        self, user_id, assertion, *, challenge, origin, rp_id
    ):
        """
        Checks whether the given assertion was produced by the given user's WebAuthn
        device.

        Returns the updated signage count on success, raises
        webauthn.AuthenticationRejectedException on failure.
        """
        user = self.get_user(user_id)

        return webauthn.verify_assertion_response(
            assertion, challenge=challenge, user=user, origin=origin, rp_id=rp_id
        )

    def add_webauthn(self, user_id, **kwargs):
        """
        Adds a WebAuthn credential to the given user.

        Returns None if the user already has this credential.
        """
        user = self.get_user(user_id)

        webauthn = WebAuthn(user=user, **kwargs)
        self.db.add(webauthn)
        self.db.flush()  # flush the db now so webauthn.id is available

        return webauthn

    def get_webauthn_by_label(self, user_id, label):
        """
        Returns a WebAuthn credential for the given user by its label,
        or None if no credential for the user has this label.
        """
        user = self.get_user(user_id)

        return next(
            (credential for credential in user.webauthn if credential.label == label),
            None,
        )

    def get_webauthn_by_credential_id(self, user_id, credential_id):
        """
        Returns a WebAuthn credential for the given user by its credential ID,
        or None of the user doesn't have a credential with this ID.
        """
        user = self.get_user(user_id)

        return next(
            (
                credential
                for credential in user.webauthn
                if credential.credential_id == credential_id
            ),
            None,
        )

    def record_event(self, user_id, *, tag, ip_address, additional=None):
        """
        Creates a new UserEvent for the given user with the given
        tag, IP address, and additional metadata.

        Returns the event.
        """
        user = self.get_user(user_id)
        return user.record_event(tag=tag, ip_address=ip_address, additional=additional)

    def generate_recovery_codes(self, user_id):
        user = self.get_user(user_id)

        if user.has_recovery_codes:
            self.db.query(RecoveryCode).filter_by(user=user).delete()

        recovery_codes = [secrets.token_hex(8) for _ in range(RECOVERY_CODE_COUNT)]
        for recovery_code in recovery_codes:
            self.db.add(RecoveryCode(user=user, code=self.hasher.hash(recovery_code)))

        self.db.flush()

        return recovery_codes

    def check_recovery_code(self, user_id, code):
        self._metrics.increment("warehouse.authentication.recovery_code.start")

        # The very first thing we want to do is check to see if we've hit our
        # global rate limit or not, assuming that we've been configured with a
        # global rate limiter anyways.
        if not self.ratelimiters["global.login"].test():
            logger.warning("Global failed login threshold reached.")
            self._metrics.increment(
                "warehouse.authentication.recovery_code.ratelimited",
                tags=["ratelimiter:global"],
            )
            raise TooManyFailedLogins(
                resets_in=self.ratelimiters["global.login"].resets_in()
            )

        # Now, check to make sure that we haven't hitten a rate limit on a
        # per user basis.
        if not self.ratelimiters["user.login"].test(user_id):
            self._metrics.increment(
                "warehouse.authentication.recovery_code.ratelimited",
                tags=["ratelimiter:user"],
            )
            raise TooManyFailedLogins(
                resets_in=self.ratelimiters["user.login"].resets_in(user_id)
            )

        user = self.get_user(user_id)

        if not user.has_recovery_codes:
            self._metrics.increment(
                "warehouse.authentication.recovery_code.failure",
                tags=["failure_reason:no_recovery_codes"],
            )
            # If we've gotten here, then we'll want to record a failed attempt in our
            # rate limiting before returning False to indicate a failed recovery code
            # verification.
            self.ratelimiters["user.login"].hit(user_id)
            self.ratelimiters["global.login"].hit()
            return False

        valid = False
        for stored_recovery_code in self.get_recovery_codes(user.id):
            if self.hasher.verify(code, stored_recovery_code.code):
                self.db.delete(stored_recovery_code)
                self.db.flush()
                valid = True

        if valid:
            self._metrics.increment("warehouse.authentication.recovery_code.ok")
        else:
            self._metrics.increment(
                "warehouse.authentication.recovery_code.failure",
                tags=["failure_reason:invalid_recovery_code"],
            )
            # If we've gotten here, then we'll want to record a failed attempt in our
            # rate limiting before returning False to indicate a failed recovery code
            # verification.
            self.ratelimiters["user.login"].hit(user_id)
            self.ratelimiters["global.login"].hit()

        return valid


@implementer(ITokenService)
class TokenService:
    def __init__(self, secret, salt, max_age):
        self.serializer = URLSafeTimedSerializer(secret, salt=salt)
        self.max_age = max_age

    def dumps(self, data):
        return self.serializer.dumps({key: str(value) for key, value in data.items()})

    def loads(self, token, return_timestamp=False):
        if not token:
            raise TokenMissing

        try:
            data = self.serializer.loads(
                token, max_age=self.max_age, return_timestamp=return_timestamp
            )
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
            "global.login": request.find_service(
                IRateLimiter, name="global.login", context=None
            ),
            "user.login": request.find_service(
                IRateLimiter, name="user.login", context=None
            ),
            "email.add": request.find_service(
                IRateLimiter, name="email.add", context=None
            ),
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

    _failure_message_preamble = "This password appears in a security breach or has been compromised and cannot be used."

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
        # The HIBP API implements a k-Anonymity scheme, by which you can take a given
        # password, hash it using sha1, and then send only the first 5 characters of the
        # hex encoded digest. This avoids leaking data to the HIBP API, because without
        # the rest of the hash, the HIBP service cannot even begin to brute force or do
        # a reverse lookup to determine what password has just been sent to it. For More
        # information see:
        #       https://www.troyhunt.com/ive-just-launched-pwned-passwords-version-2/

        self._metrics_increment("warehouse.compromised_password_check.start", tags=tags)

        # To work with the HIBP API, we need the sha1 of the UTF8 encoded password.
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
        # That is, it is a line delimited textual data, where each line is a hash, a
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
