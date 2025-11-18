# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import collections
import datetime
import functools
import hashlib
import http
import logging
import os
import secrets
import typing
import urllib.parse

import passlib.exc
import pytz
import requests

from linehaul.ua import parser as linehaul_user_agent_parser
from passlib.context import CryptContext
from sqlalchemy import exists, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import joinedload
from ua_parser import user_agent_parser
from webauthn.helpers import bytes_to_base64url
from zope.interface import implementer

import warehouse.utils.otp as otp
import warehouse.utils.webauthn as webauthn

from warehouse.accounts.interfaces import (
    BurnedRecoveryCode,
    IDomainStatusService,
    IEmailBreachedService,
    InvalidRecoveryCode,
    IPasswordBreachedService,
    ITokenService,
    IUserService,
    NoRecoveryCodes,
    TokenExpired,
    TokenInvalid,
    TokenMissing,
    TooManyEmailsAdded,
    TooManyFailedLogins,
)
from warehouse.accounts.models import (
    DisableReason,
    Email,
    ProhibitedUserName,
    RecoveryCode,
    TermsOfServiceEngagement,
    UniqueLoginStatus,
    User,
    UserTermsOfServiceEngagement,
    UserUniqueLogin,
    WebAuthn,
)
from warehouse.email import send_unrecognized_login_email
from warehouse.events.models import UserAgentInfo
from warehouse.events.tags import EventTag
from warehouse.metrics import IMetricsService
from warehouse.rate_limiting import DummyRateLimiter, IRateLimiter
from warehouse.utils.crypto import BadData, SignatureExpired, URLSafeTimedSerializer

if typing.TYPE_CHECKING:
    from pyramid.request import Request

logger = logging.getLogger(__name__)

PASSWORD_FIELD = "password"
RECOVERY_CODE_COUNT = 8
RECOVERY_CODE_BYTES = 8


@implementer(IUserService)
class DatabaseUserService:
    def __init__(self, session, *, ratelimiters=None, remote_addr, metrics):
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
        self.remote_addr = remote_addr
        self._metrics = metrics
        self.cached_get_user = functools.lru_cache(self._get_user)

    def _get_user(self, userid):
        # TODO: We probably don't actually want to just return the database
        #       object here.
        # TODO: We need some sort of Anonymous User.
        return (
            self.db.scalars(
                select(User).options(joinedload(User.webauthn)).where(User.id == userid)
            )
            .unique()
            .one_or_none()
        )

    def get_user(self, userid):
        return self.cached_get_user(userid)

    @functools.lru_cache
    def get_user_by_username(self, username):
        user_id = self.find_userid(username)
        return None if user_id is None else self.get_user(user_id)

    @functools.lru_cache
    def get_user_by_email(self, email: str) -> User | None:
        user_id = self.find_userid_by_email(email)
        return None if user_id is None else self.get_user(user_id)

    @functools.lru_cache
    def get_users_by_prefix(self, prefix: str) -> list[User]:
        """
        Get the first 10 matches by username prefix.
        No need to apply `ILIKE` here, as the `username` column is already
        `CIText`.
        """
        return (
            self.db.query(User)
            .filter(User.username.startswith(prefix))
            .order_by(User.username)
            .limit(10)
            .all()
        )

    @functools.lru_cache
    def get_admin_user(self):
        """Useful for notifications to the admin@ email address."""
        return self.get_user_by_username("admin")

    def username_is_prohibited(self, username):
        return self.db.query(
            exists().where(ProhibitedUserName.name == username.lower())
        ).scalar()

    @functools.lru_cache
    def find_userid(self, username):
        try:
            user = self.db.query(User.id).filter(User.username == username).one()
        except NoResultFound:
            return

        return user.id

    @functools.lru_cache
    def find_userid_by_email(self, email):
        try:
            user_id = (self.db.query(Email.user_id).filter(Email.email == email).one())[
                0
            ]
        except NoResultFound:
            return

        return user_id

    def _check_ratelimits(self, userid=None, tags=None):
        tags = tags if tags is not None else []

        # First we want to check if a single IP is exceeding our rate limiter.
        if self.remote_addr is not None:
            if not self.ratelimiters["ip.login"].test(self.remote_addr):
                logger.warning("IP failed login threshold reached.")
                self._metrics.increment(
                    "warehouse.authentication.ratelimited",
                    tags=tags + ["ratelimiter:ip"],
                )
                raise TooManyFailedLogins(
                    resets_in=self.ratelimiters["ip.login"].resets_in(self.remote_addr)
                )

        # Next check to see if we've hit our global rate limit or not,
        # assuming that we've been configured with a global rate limiter anyways.
        if not self.ratelimiters["global.login"].test():
            logger.warning("Global failed login threshold reached.")
            self._metrics.increment(
                "warehouse.authentication.ratelimited",
                tags=tags + ["ratelimiter:global"],
            )
            raise TooManyFailedLogins(
                resets_in=self.ratelimiters["global.login"].resets_in()
            )

        # Now, check to make sure that we haven't hitten a rate limit on a
        # per user basis.
        if userid is not None:
            if not self.ratelimiters["user.login"].test(userid):
                self._metrics.increment(
                    "warehouse.authentication.ratelimited",
                    tags=tags + ["ratelimiter:user"],
                )
                raise TooManyFailedLogins(
                    resets_in=self.ratelimiters["user.login"].resets_in(userid)
                )

    def _hit_ratelimits(self, userid=None):
        if userid is not None:
            self.ratelimiters["user.login"].hit(userid)
        self.ratelimiters["global.login"].hit()
        self.ratelimiters["ip.login"].hit(self.remote_addr)

    def _check_2fa_ratelimits(self, userid: int, tags: list[str] | None = None) -> None:
        tags = tags if tags is not None else []

        # Check IP-based 2FA rate limit
        if self.remote_addr is not None:
            if not self.ratelimiters["2fa.ip"].test(self.remote_addr):
                logger.warning("IP failed 2FA threshold reached.")
                self._metrics.increment(
                    "warehouse.authentication.ratelimited",
                    tags=tags + ["ratelimiter:ip"],
                )
                raise TooManyFailedLogins(
                    resets_in=self.ratelimiters["2fa.ip"].resets_in(self.remote_addr)
                )

        # Check user-based 2FA rate limit
        if not self.ratelimiters["2fa.user"].test(userid):
            logger.warning("User failed 2FA threshold reached.")
            self._metrics.increment(
                "warehouse.authentication.ratelimited",
                tags=tags + ["ratelimiter:user"],
            )
            raise TooManyFailedLogins(
                resets_in=self.ratelimiters["2fa.user"].resets_in(userid)
            )

    def _hit_2fa_ratelimits(self, userid: int) -> None:
        self.ratelimiters["2fa.user"].hit(userid)
        if self.remote_addr is not None:
            self.ratelimiters["2fa.ip"].hit(self.remote_addr)

    def check_password(self, userid, password, *, tags=None):
        tags = tags if tags is not None else []
        tags.append("mechanism:check_password")

        self._metrics.increment("warehouse.authentication.start", tags=tags)

        self._check_ratelimits(userid=None, tags=tags)

        user = self.get_user(userid)
        if user is not None:
            self._check_ratelimits(userid=user.id, tags=tags)

            # Actually check our hash, optionally getting a new hash for it if
            # we should upgrade our saved hashed.
            try:
                ok, new_hash = self.hasher.verify_and_update(password, user.password)
            except passlib.exc.PasswordValueError:
                ok = False

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
        self._hit_ratelimits(userid=(user.id if user is not None else None))
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
        primary=None,
        verified=False,
        public=False,
        ratelimit=True,
    ):
        if ratelimit:
            # Check to make sure that we haven't hitten the rate limit for this IP
            if not self.ratelimiters["email.add"].test(self.remote_addr):
                self._metrics.increment(
                    "warehouse.email.add.ratelimited", tags=["ratelimiter:email.add"]
                )
                raise TooManyEmailsAdded(
                    resets_in=self.ratelimiters["email.add"].resets_in(self.remote_addr)
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

        if ratelimit:
            self.ratelimiters["email.add"].hit(self.remote_addr)
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

    def disable_password(self, user_id, request, reason=None):
        user = self.get_user(user_id)
        user.password = self.hasher.disable()
        user.disabled_for = reason
        user.record_event(
            tag=EventTag.Account.PasswordDisabled,
            request=request,
            additional={"reason": reason.value if reason else None},
        )

    def is_disabled(self, user_id):
        user = self.get_user(user_id)

        if user.is_frozen:
            return (True, DisableReason.AccountFrozen)

        # User is disabled due to password being disabled
        if not self.hasher.is_enabled(user.password):
            return (True, user.disabled_for)

        # User is not disabled.
        return (False, None)

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
        """
        Returns all recovery codes for the user
        """
        user = self.get_user(user_id)

        stored_recovery_codes = self.db.query(RecoveryCode).filter_by(user=user).all()

        if stored_recovery_codes:
            return stored_recovery_codes

        self._metrics.increment(
            "warehouse.authentication.recovery_code.failure",
            tags=["failure_reason:no_recovery_codes"],
        )
        # If we've gotten here, then we'll want to record a failed attempt in our
        # rate limiting before raising an exception to indicate a failed
        # recovery code verification.
        self._hit_2fa_ratelimits(userid=user_id)
        raise NoRecoveryCodes

    def get_recovery_code(self, user_id, code):
        """
        Returns a specific recovery code if it exists
        """
        user = self.get_user(user_id)

        for stored_recovery_code in self.get_recovery_codes(user.id):
            if self.hasher.verify(code, stored_recovery_code.code):
                return stored_recovery_code

        self._metrics.increment(
            "warehouse.authentication.recovery_code.failure",
            tags=["failure_reason:invalid_recovery_code"],
        )
        # If we've gotten here, then we'll want to record a failed attempt in our
        # rate limiting before returning False to indicate a failed recovery code
        # verification.
        self._hit_2fa_ratelimits(userid=user_id)
        raise InvalidRecoveryCode

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
        tags.append("mechanism:check_totp_value")
        self._metrics.increment("warehouse.authentication.two_factor.start", tags=tags)

        self._check_2fa_ratelimits(userid=user_id, tags=tags)

        totp_secret = self.get_totp_secret(user_id)

        if totp_secret is None:
            self._metrics.increment(
                "warehouse.authentication.two_factor.failure",
                tags=tags + ["failure_reason:no_totp"],
            )
            # If we've gotten here, then we'll want to record a failed attempt in our
            # rate limiting before returning False to indicate a failed totp
            # verification.
            self._hit_2fa_ratelimits(userid=user_id)
            return False

        last_totp_value = self.get_last_totp_value(user_id)

        if last_totp_value is not None and totp_value == last_totp_value.encode():
            return False

        try:
            if not (valid := otp.verify_totp(totp_secret, totp_value)):
                self._hit_2fa_ratelimits(userid=user_id)
        except otp.OutOfSyncTOTPError:
            self._metrics.increment(
                "warehouse.authentication.two_factor.failure",
                tags=tags + ["failure_reason:out_of_sync"],
            )
            self._hit_2fa_ratelimits(userid=user_id)
            raise otp.OutOfSyncTOTPError
        except otp.InvalidTOTPError:
            self._metrics.increment(
                "warehouse.authentication.two_factor.failure",
                tags=tags + ["failure_reason:invalid_totp"],
            )
            # If we've gotten here, then we'll want to record a failed attempt in our
            # rate limiting before raising to indicate a failed totp verification.
            self._hit_2fa_ratelimits(userid=user_id)
            raise otp.InvalidTOTPError

        self._metrics.increment("warehouse.authentication.two_factor.ok", tags=tags)
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
        webauthn.RegistrationRejectedError on failure.
        """
        validated_credential = webauthn.verify_registration_response(
            credential, challenge=challenge, rp_id=rp_id, origin=origin
        )

        webauthn_cred = (
            self.db.query(WebAuthn)
            .filter_by(
                credential_id=bytes_to_base64url(validated_credential.credential_id)
            )
            .first()
        )

        if webauthn_cred is not None:
            raise webauthn.RegistrationRejectedError("Credential ID already in use")

        return validated_credential

    def verify_webauthn_assertion(
        self, user_id, assertion, *, challenge, origin, rp_id
    ):
        """
        Checks whether the given assertion was produced by the given user's WebAuthn
        device.

        Returns the updated signage count on success, raises
        webauthn.AuthenticationRejectedError on failure.
        """
        # Check rate limits before attempting verification
        self._check_2fa_ratelimits(userid=user_id, tags=["mechanism:webauthn"])

        user = self.get_user(user_id)

        try:
            return webauthn.verify_assertion_response(
                assertion, challenge=challenge, user=user, origin=origin, rp_id=rp_id
            )
        except webauthn.AuthenticationRejectedError:
            # Hit rate limits on failure
            self._hit_2fa_ratelimits(userid=user_id)
            raise

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

    def generate_recovery_codes(self, user_id):
        user = self.get_user(user_id)

        if user.has_recovery_codes:
            self.db.query(RecoveryCode).filter_by(user=user).delete()

        recovery_codes = [
            secrets.token_hex(RECOVERY_CODE_BYTES) for _ in range(RECOVERY_CODE_COUNT)
        ]
        for recovery_code in recovery_codes:
            self.db.add(RecoveryCode(user=user, code=self.hasher.hash(recovery_code)))

        return recovery_codes

    def check_recovery_code(self, user_id, code, skip_ratelimits=False):
        self._metrics.increment("warehouse.authentication.recovery_code.start")

        if not skip_ratelimits:
            self._check_2fa_ratelimits(
                userid=user_id,
                tags=["mechanism:check_recovery_code"],
            )

        user = self.get_user(user_id)
        stored_recovery_code = self.get_recovery_code(user.id, code)

        if stored_recovery_code.burned:
            self._metrics.increment(
                "warehouse.authentication.recovery_code.failure",
                tags=["failure_reason:burned_recovery_code"],
            )
            raise BurnedRecoveryCode

        # The code is valid and not burned. Mark it as burned
        stored_recovery_code.burned = datetime.datetime.now()
        self._metrics.increment("warehouse.authentication.recovery_code.ok")
        return True

    def get_password_timestamp(self, user_id):
        user = self.get_user(user_id)
        return user.password_date.timestamp() if user.password_date is not None else 0

    def needs_tos_flash(self, user_id, revision):
        """
        Check if we need to flash a ToS update to user on login.
        """
        query = self.db.query(UserTermsOfServiceEngagement).filter(
            UserTermsOfServiceEngagement.user_id == user_id,
            UserTermsOfServiceEngagement.revision == revision,
        )

        # Find all instances of an engagement with the Terms of Service more than 30
        # days ago. If we find any, the ToS are already in effect for the user by
        # default so they do not need to be flashed.
        engagements_30_days_before_tos_active = (
            query.filter(
                UserTermsOfServiceEngagement.created
                < datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=30)
            )
            .order_by(
                UserTermsOfServiceEngagement.created,
            )
            .first()
        )
        if engagements_30_days_before_tos_active is not None:
            return False

        # Find any active engagements with the Terms of Service. If the user has
        # actively engaged with the updated Terms of Service we skip flashing the
        # update banner.
        active_engagements = query.filter(
            UserTermsOfServiceEngagement.engagement.in_(
                [TermsOfServiceEngagement.Viewed, TermsOfServiceEngagement.Agreed]
            )
        ).first()
        if active_engagements is None:
            return True

        return False

    def record_tos_engagement(
        self,
        user_id,
        revision: str,
        engagement: TermsOfServiceEngagement,
    ) -> None:
        """
        Add a record of end user being flashed about, notified of, viewing, or agreeing
        to a terms of service change.
        """
        if not isinstance(engagement, TermsOfServiceEngagement):
            raise ValueError(f"{engagement} is not a TermsOfServiceEngagement")
        self.db.add(
            UserTermsOfServiceEngagement(
                user_id=user_id,
                revision=revision,
                created=datetime.datetime.now(datetime.UTC),
                engagement=engagement,
            )
        )

    def device_is_known(self, userid, request):
        user = self.get_user(userid)
        token_service = request.find_service(ITokenService, name="confirm_login")
        unique_login = (
            request.db.query(UserUniqueLogin)
            .filter(
                UserUniqueLogin.user_id == userid,
                UserUniqueLogin.ip_address == request.remote_addr,
            )
            .one_or_none()
        )
        should_send_email = False

        # Check if we've seen this device and it's been confirmed
        if unique_login and unique_login.status == UniqueLoginStatus.CONFIRMED:
            return True

        # Create a new login if we haven't seen this device before
        if not unique_login:
            unique_login = UserUniqueLogin(
                user_id=userid,
                ip_address=request.remote_addr,
                status=UniqueLoginStatus.PENDING,
            )
            request.db.add(unique_login)
            request.db.flush()  # To get the ID for the token
            should_send_email = True

        # Check if the login had expired
        if unique_login.expires and unique_login.expires < datetime.datetime.now(
            datetime.UTC
        ):
            # The previous token has expired, update the expiry for
            # the login and re-send the email
            unique_login.expires = datetime.datetime.now(
                datetime.UTC
            ) + datetime.timedelta(seconds=token_service.max_age)
            should_send_email = True

        # If we don't need to send an email, short-circuit
        if not should_send_email:
            return False

        # Get User Agent Information
        user_agent_info_data = {}
        if user_agent_str := request.headers.get("User-Agent"):
            user_agent_info_data = {
                # A hack to get it to fall back to the raw user agent
                "installer": user_agent_str,
            }
            try:
                parsed = linehaul_user_agent_parser.parse(user_agent_str)
                if parsed and parsed.installer and parsed.installer.name == "Browser":
                    parsed_ua = user_agent_parser.Parse(user_agent_str)
                    user_agent_info_data = {
                        "installer": "Browser",
                        "device": parsed_ua["device"]["family"],
                        "os": parsed_ua["os"]["family"],
                        "user_agent": parsed_ua["user_agent"]["family"],
                    }
            except linehaul_user_agent_parser.UnknownUserAgentError:
                pass  # Fallback to raw user-agent string

        user_agent_info = UserAgentInfo(**user_agent_info_data)

        # Generate a token
        token = token_service.dumps(
            {
                "action": "login-confirmation",
                "user.id": str(user.id),
                "user.last_login": str(
                    user.last_login or datetime.datetime.min.replace(tzinfo=pytz.UTC)
                ),
                "unique_login_id": unique_login.id,
            }
        )

        # Send the email
        send_unrecognized_login_email(
            request,
            user,
            ip_address=request.remote_addr,
            user_agent=user_agent_info.display(),
            token=token,
        )

        return False


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
        except BadData:  # Catch all other exceptions
            raise TokenInvalid

        return data

    def unsafe_load_payload(self, token):
        """
        ¡DANGER!

        This method does not validate expiration whatsoever!
        It can *and should* only be used for inspecting an expired token then
        doing nothing with it whatsoever.
        """
        signature_valid, data = self.serializer.loads_unsafe(token)

        if signature_valid:
            return data
        return None


def database_login_factory(context, request):
    return DatabaseUserService(
        request.db,
        metrics=request.find_service(IMetricsService, context=None),
        remote_addr=request.remote_addr,
        ratelimiters={
            "ip.login": request.find_service(
                IRateLimiter, name="ip.login", context=None
            ),
            "global.login": request.find_service(
                IRateLimiter, name="global.login", context=None
            ),
            "user.login": request.find_service(
                IRateLimiter, name="user.login", context=None
            ),
            "2fa.ip": request.find_service(IRateLimiter, name="2fa.ip", context=None),
            "2fa.user": request.find_service(
                IRateLimiter, name="2fa.user", context=None
            ),
            "email.add": request.find_service(
                IRateLimiter, name="email.add", context=None
            ),
            "password.reset": request.find_service(
                IRateLimiter, name="password.reset", context=None
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
    _failure_message_preamble = (
        "This password appears in a security breach or has been "
        "compromised and cannot be used."
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

    def _metrics_increment(self, *args, **kwargs):
        self._metrics.increment(*args, **kwargs)

    def _get_url(self, prefix):
        return urllib.parse.urljoin(self._api_base, os.path.join("/range/", prefix))

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
        hashed_password = (
            hashlib.sha1(password.encode("utf8"), usedforsecurity=False)
            .hexdigest()
            .lower()
        )

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

    @classmethod
    def create_service(cls, context, request):
        return cls()

    def check_password(self, password, *, tags=None):
        # This service allows *every* password as a non-breached password. It will never
        # tell a user their password isn't good enough.
        return False


@implementer(IEmailBreachedService)
class HaveIBeenPwnedEmailBreachedService:
    def __init__(
        self,
        *,
        session,
        api_base="https://haveibeenpwned.com/api/v3/breachedaccount/",
        api_key=None,
    ):
        self._http = session
        self._api_base = api_base
        self.api_key = api_key

    @classmethod
    def create_service(cls, context, request):
        hibp_api_key = request.registry.settings.get("hibp.api_key")
        return cls(session=request.http, api_key=hibp_api_key)

    def get_email_breach_count(self, email: str) -> int | None:
        """
        Check if an email has been breached, return the number of breaches.
        See https://haveibeenpwned.com/API/v3#BreachesForAccount
        """

        # bail early if no api key is set, so we don't send failing requests
        if not self.api_key:
            return None

        try:
            resp = self._http.get(
                urllib.parse.urljoin(self._api_base, email),
                headers={"User-Agent": "PyPI.org", "hibp-api-key": self.api_key},
                timeout=(0.25, 0.25),
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            # 404 is expected if the email has **not** been breached
            if (
                exc.response is not None
                and exc.response.status_code == http.HTTPStatus.NOT_FOUND
            ):
                return 0
            logger.warning("Error contacting HaveIBeenPwned: %r", exc)
            return -1

        return len(resp.json())


@implementer(IEmailBreachedService)
class NullEmailBreachedService:
    @classmethod
    def create_service(cls, context, request):
        return cls()

    def get_email_breach_count(self, email):
        # This service allows *every* email as a non-breached email.
        return 0


@implementer(IDomainStatusService)
class NullDomainStatusService:
    @classmethod
    def create_service(cls, _context, _request):
        return cls()

    def get_domain_status(self, _domain: str) -> list[str]:
        return ["active"]


@implementer(IDomainStatusService)
class DomainrDomainStatusService:
    def __init__(self, session, client_id):
        self._http = session
        self.client_id = client_id

    @classmethod
    def create_service(cls, _context, request: Request) -> DomainrDomainStatusService:
        domainr_client_id = request.registry.settings.get("domain_status.client_id")
        return cls(session=request.http, client_id=domainr_client_id)

    def get_domain_status(self, domain: str) -> list[str] | None:
        """
        Check if a domain is available or not.
        See https://domainr.com/docs/api/v2/status
        """
        try:
            resp = self._http.get(
                "https://api.domainr.com/v2/status",
                params={"client_id": self.client_id, "domain": domain},
                timeout=5,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Error contacting Domainr: %r", exc)
            return None

        if errors := resp.json().get("errors"):
            logger.warning(
                {"status": "Error from Domainr", "errors": errors, "domain": domain}
            )
            return None

        return resp.json()["status"][0]["status"].split()
