# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import typing
import warnings

import jwt
import redis
import requests
import sentry_sdk

from zope.interface import implementer

from warehouse.metrics.interfaces import IMetricsService
from warehouse.oidc.errors import InvalidPublisherError
from warehouse.oidc.interfaces import IOIDCPublisherService, SignedClaims
from warehouse.oidc.models import OIDCPublisher, PendingOIDCPublisher
from warehouse.oidc.utils import OIDC_PUBLISHER_CLASSES, find_publisher_by_issuer
from warehouse.utils.exceptions import InsecureOIDCPublisherWarning

# Maximum clock-skew tolerance (in seconds) applied when verifying JWT expiration.
# PyJWT will accept tokens up to this many seconds past their ``exp`` claim.
# This value is shared with ``store_jwt_identifier`` so the Redis anti-replay
# key always outlives the window in which the token is accepted.
_JWT_LEEWAY = 30

if typing.TYPE_CHECKING:
    from pyramid.request import Request
    from sqlalchemy.orm import Session

    from warehouse.packaging import Project


@implementer(IOIDCPublisherService)
class OIDCPublisherService:
    def __init__(
        self,
        session: Session,
        publisher: str,
        issuer_url: str,
        audience: str,
        cache_url: str,
        metrics: IMetricsService,
    ):
        self.db = session
        self.publisher = publisher
        self.issuer_url = issuer_url
        self.audience = audience
        self.cache_url = cache_url
        self.metrics = metrics

    def _store_keyset(self, issuer_url: str, keys: dict) -> None:
        """
        Store the given keyset for the given **issuer**, setting the timeout key
        in the process.
        """
        _publisher_jwk_key = f"/warehouse/oidc/jwks/{issuer_url}"
        _publisher_timeout_key = f"{_publisher_jwk_key}/timeout"

        with redis.StrictRedis.from_url(self.cache_url) as r:
            r.set(_publisher_jwk_key, json.dumps(keys))
            r.setex(_publisher_timeout_key, 60, "placeholder")

    def _get_keyset(self, issuer_url: str) -> tuple[dict[str, dict], bool]:
        """
        Return the cached keyset for the given issuer, or an empty
        keyset if no keys are currently cached.
        """
        _publisher_jwk_key = f"/warehouse/oidc/jwks/{issuer_url}"
        _publisher_timeout_key = f"{_publisher_jwk_key}/timeout"

        with redis.StrictRedis.from_url(self.cache_url) as r:
            keys = r.get(_publisher_jwk_key)
            timeout = bool(r.exists(_publisher_timeout_key))
            if keys is not None:
                return json.loads(keys), timeout
            else:
                return {}, timeout

    def _refresh_keyset(self, issuer_url: str) -> dict[str, dict]:
        """
        Attempt to refresh the keyset from the OIDC issuer, assuming no
        timeout is in effect.

        Returns the refreshed keyset, or the cached keyset if a timeout is
        in effect.

        Returns the cached keyset on any publisher access or format errors.
        """

        # Fast path: we're in a cooldown from a previous refresh.
        keys, timeout = self._get_keyset(issuer_url=issuer_url)
        if timeout:
            self.metrics.increment(
                "warehouse.oidc.refresh_keyset.timeout",
                tags=[f"publisher:{self.publisher}", f"issuer_url:{issuer_url}"],
            )
            return keys

        oidc_url = f"{issuer_url}/.well-known/openid-configuration"

        resp = requests.get(oidc_url, timeout=5)

        # For whatever reason, an OIDC publisher's configuration URL might be
        # offline. We don't want to completely explode here, since other
        # publishers might still be online (and need updating), so we spit
        # out an error and return None instead of raising.
        if not resp.ok:
            sentry_sdk.capture_message(
                f"OIDC publisher {self.publisher} failed to return configuration: "
                f"{oidc_url}"
            )
            return keys

        oidc_conf = resp.json()
        jwks_url = oidc_conf.get("jwks_uri")

        # A valid OIDC configuration MUST have a `jwks_uri`, but we
        # defend against its absence anyways.
        if jwks_url is None:
            sentry_sdk.capture_message(
                f"OIDC publisher {self.publisher} is returning malformed "
                "configuration (no jwks_uri)"
            )
            return keys

        resp = requests.get(jwks_url, timeout=5)

        # Same reasoning as above.
        if not resp.ok:
            sentry_sdk.capture_message(
                f"OIDC publisher {self.publisher} failed to return JWKS JSON: "
                f"{jwks_url}"
            )
            return keys

        jwks_conf = resp.json()
        new_keys = jwks_conf.get("keys")

        # Another sanity test: an OIDC publisher should never return an empty
        # keyset, but there's nothing stopping them from doing so. We don't
        # want to cache an empty keyset just in case it's a short-lived error,
        # so we check here, error, and return the current cache instead.
        if not new_keys:
            sentry_sdk.capture_message(
                f"OIDC publisher {self.publisher} returned JWKS JSON but no keys"
            )
            return keys

        keys = {key["kid"]: key for key in new_keys}
        self._store_keyset(issuer_url, keys)

        return keys

    def _get_key(self, key_id: str, issuer_url: str) -> jwt.PyJWK:
        """
        Return a JWK for the given key ID, or None if the key can't be found
        in this publisher's keyset.
        """

        keyset, _ = self._get_keyset(issuer_url)
        if key_id not in keyset:
            keyset = self._refresh_keyset(issuer_url)
        if key_id not in keyset:
            self.metrics.increment(
                "warehouse.oidc.get_key.error",
                tags=[
                    f"publisher:{self.publisher}",
                    f"key_id:{key_id}",
                    f"issuer_url:{self.issuer_url}",
                ],
            )
            raise jwt.PyJWTError(
                f"Key ID {key_id!r} not found for issuer {issuer_url!r}"
            )
        return jwt.PyJWK(keyset[key_id])

    def _get_key_for_token(self, token, issuer_url: str) -> jwt.PyJWK:
        """
        Return a JWK suitable for verifying the given JWT.

        The JWT is not verified at this point, and this step happens
        prior to any verification.
        """
        unverified_header = jwt.get_unverified_header(token)
        return self._get_key(unverified_header["kid"], issuer_url)

    def jwt_identifier_exists(self, jti: str) -> bool:
        """
        Check if a JWT Token Identifier has already been used.
        """
        with redis.StrictRedis.from_url(self.cache_url) as r:
            return bool(r.exists(f"/warehouse/oidc/{self.issuer_url}/{jti}"))

    def store_jwt_identifier(self, jti: str, expiration: int) -> bool:
        """
        Atomically store the JTI if it does not already exist.

        Returns True if the JTI was newly stored, False if it already existed.
        """
        with redis.StrictRedis.from_url(self.cache_url) as r:
            # The key must outlive the full window during which PyJWT accepts
            # the token. PyJWT allows up to ``_JWT_LEEWAY`` seconds past
            # ``exp``, so we add an extra 5-second margin on top.
            result = r.set(
                f"/warehouse/oidc/{self.issuer_url}/{jti}",
                exat=expiration + _JWT_LEEWAY + 5,
                value="",  # empty value to lower memory usage
                nx=True,
            )
            # r.set(..., nx=True) returns True if key was created, None if exists
            return result is True

    def verify_jwt_signature(
        self, unverified_token: str, issuer_url: str
    ) -> SignedClaims | None:
        """
        Verify the signature of the given JWT, returning the signed claims.
        """
        try:
            key = self._get_key_for_token(unverified_token, issuer_url)
        except jwt.PyJWTError:
            # The user might feed us an entirely nonsense JWT, e.g. one
            # with missing components.
            self.metrics.increment(
                "warehouse.oidc.verify_jwt_signature.malformed_jwt",
                tags=[f"publisher:{self.publisher}", f"issuer_url:{issuer_url}"],
            )
            return None

        try:
            # NOTE: Many of the keyword arguments here are defaults, but we
            # set them explicitly to assert the intended verification behavior.
            signed_payload = jwt.decode(
                unverified_token,
                key=key,
                algorithms=["RS256"],
                options=dict(
                    verify_signature=True,
                    # "require" only checks for the presence of these claims, not
                    # their validity. Each has a corresponding "verify_" kwarg
                    # that enforces their actual validity.
                    require=["iss", "iat", "exp", "aud"],
                    verify_iss=True,
                    verify_iat=True,
                    verify_exp=True,
                    verify_aud=True,
                    # We don't require the nbf claim, but verify it if present
                    verify_nbf=True,
                    # We don't accept JWTs with multiple audiences; we
                    # want to be the ONLY audience listed.
                    strict_aud=True,
                ),
                issuer=issuer_url,
                audience=self.audience,
                leeway=_JWT_LEEWAY,
            )
            return SignedClaims(signed_payload)
        except Exception as e:
            self.metrics.increment(
                "warehouse.oidc.verify_jwt_signature.invalid_signature",
                tags=[f"publisher:{self.publisher}", f"issuer_url:{issuer_url}"],
            )
            if not isinstance(e, jwt.PyJWTError):
                with sentry_sdk.new_scope() as scope:
                    scope.fingerprint = [e]
                    # We expect pyjwt to only raise subclasses of PyJWTError, but
                    # we can't enforce this. Other exceptions indicate an abstraction
                    # leak, so we log them for upstream reporting.
                    sentry_sdk.capture_message(f"JWT backend raised generic error: {e}")
            return None

    def find_publisher(
        self, signed_claims: SignedClaims, *, pending: bool = False
    ) -> OIDCPublisher | PendingOIDCPublisher:
        """Returns a publisher for the given claims, or raises an error."""
        metrics_tags = [
            f"publisher:{self.publisher}",
            f"issuer_url:{signed_claims['iss']}",
        ]
        self.metrics.increment(
            "warehouse.oidc.find_publisher.attempt",
            tags=metrics_tags,
        )

        # Verify that the JWT's issuer matches this service's canonical issuer URL,
        # unless the publisher type supports custom issuers. Providers like GitLab
        # filter by issuer_url in lookup_by_claims, so a self-managed instance can
        # only match publishers explicitly registered with that custom issuer URL.
        # Providers like GitHub do NOT filter by issuer URL in lookup_by_claims,
        # so without this check a compromised custom issuer (e.g. GHES) could forge
        # JWTs matching any canonical publisher.
        if signed_claims["iss"] != self.issuer_url and not (
            OIDC_PUBLISHER_CLASSES[self.issuer_url][pending].__supports_custom_issuer__
        ):
            self.metrics.increment(
                "warehouse.oidc.find_publisher.issuer_url_mismatch",
                tags=metrics_tags,
            )
            raise InvalidPublisherError(
                f"JWT issuer {signed_claims['iss']!r} does not match "
                f"expected issuer {self.issuer_url!r}"
            )

        try:
            publisher = find_publisher_by_issuer(
                self.db, self.issuer_url, signed_claims, pending=pending
            )

            publisher.verify_claims(signed_claims, self)
            self.metrics.increment(
                "warehouse.oidc.find_publisher.ok",
                tags=metrics_tags,
            )

            return publisher
        except InvalidPublisherError as e:
            self.metrics.increment(
                "warehouse.oidc.find_publisher.publisher_not_found",
                tags=metrics_tags,
            )
            raise e

    def reify_pending_publisher(
        self, pending_publisher: PendingOIDCPublisher, project: Project
    ) -> OIDCPublisher:
        new_publisher = pending_publisher.reify(self.db)
        project.oidc_publishers.append(new_publisher)
        return new_publisher


class OIDCPublisherServiceFactory:
    def __init__(
        self,
        publisher: str,
        issuer_url: str,
        service_class=OIDCPublisherService,  # TODO: Unclear how to correctly type this
    ):
        self.publisher = publisher
        self.issuer_url = issuer_url
        self.service_class = service_class

    def __call__(self, _context, request: Request) -> OIDCPublisherService:
        cache_url = request.registry.settings["oidc.jwk_cache_url"]
        audience = request.registry.settings["warehouse.oidc.audience"]
        metrics = request.find_service(IMetricsService, context=None)

        return self.service_class(
            request.db,
            self.publisher,
            self.issuer_url,
            audience,
            cache_url,
            metrics,
        )

    def __eq__(self, other) -> bool:
        if not isinstance(other, OIDCPublisherServiceFactory):
            return NotImplemented

        return (self.publisher, self.issuer_url, self.service_class) == (
            other.publisher,
            other.issuer_url,
            other.service_class,
        )


class NullOIDCPublisherService(OIDCPublisherService):
    """
    A development-only OIDC publisher service that skips JWT signature
    verification and JTI replay tracking, but uses the real find_publisher
    and verify_claims logic.
    """

    def __init__(self, *args, **kwargs):
        warnings.warn(
            "NullOIDCPublisherService is intended only for use in development, "
            "you should not use it in production due to the lack of actual "
            "JWT verification.",
            InsecureOIDCPublisherWarning,
        )
        super().__init__(*args, **kwargs)

    def verify_jwt_signature(
        self, unverified_token: str, issuer_url: str
    ) -> SignedClaims | None:
        try:
            return SignedClaims(
                jwt.decode(
                    unverified_token,
                    options=dict(
                        verify_signature=False,
                        # We require all of these to be present, but for the
                        # null publisher we only actually verify the audience.
                        require=["iss", "iat", "exp", "aud"],
                        verify_iss=False,
                        verify_iat=False,
                        verify_exp=False,
                        verify_aud=True,
                        # We don't accept JWTs with multiple audiences; we
                        # want to be the ONLY audience listed.
                        strict_aud=True,
                    ),
                    audience=self.audience,
                )
            )
        except jwt.PyJWTError:
            return None

    def jwt_identifier_exists(self, jti: str) -> bool:
        """
        The NullOIDCPublisherService does not provide a mechanism to store used
        tokens before their expiration.
        """
        return False

    def store_jwt_identifier(self, jti: str, expiration: int) -> bool:
        """
        The NullOIDCPublisherService does not provide a mechanism to store used
        tokens before their expiration.
        """
        return True
