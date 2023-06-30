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

import json
import warnings

import jwt
import redis
import requests
import sentry_sdk

from zope.interface import implementer

from warehouse.metrics.interfaces import IMetricsService
from warehouse.oidc.interfaces import IOIDCPublisherService, SignedClaims
from warehouse.oidc.models import OIDCPublisher, PendingOIDCPublisher
from warehouse.oidc.utils import find_publisher_by_issuer
from warehouse.utils.exceptions import InsecureOIDCPublisherWarning


@implementer(IOIDCPublisherService)
class NullOIDCPublisherService:
    def __init__(self, session, publisher, issuer_url, audience, cache_url, metrics):
        warnings.warn(
            "NullOIDCPublisherService is intended only for use in development, "
            "you should not use it in production due to the lack of actual "
            "JWT verification.",
            InsecureOIDCPublisherWarning,
        )

        self.db = session
        self.issuer_url = issuer_url

    def verify_jwt_signature(self, unverified_token: str) -> SignedClaims | None:
        try:
            return SignedClaims(
                jwt.decode(
                    unverified_token,
                    options=dict(
                        verify_signature=False,
                        # We require all of these to be present, but for the
                        # null publisher we only actually verify the audience.
                        require=["iss", "iat", "nbf", "exp", "aud"],
                        verify_iss=False,
                        verify_iat=False,
                        verify_nbf=False,
                        verify_exp=False,
                        verify_aud=True,
                    ),
                    audience="pypi",
                )
            )
        except jwt.PyJWTError:
            return None

    def find_publisher(
        self, signed_claims: SignedClaims, *, pending: bool = False
    ) -> OIDCPublisher | PendingOIDCPublisher | None:
        # NOTE: We do NOT verify the claims against the publisher, since this
        # service is for development purposes only.
        return find_publisher_by_issuer(
            self.db, self.issuer_url, signed_claims, pending=pending
        )

    def reify_pending_publisher(self, pending_publisher, project):
        new_publisher = pending_publisher.reify(self.db)
        project.oidc_publishers.append(new_publisher)
        return new_publisher


@implementer(IOIDCPublisherService)
class OIDCPublisherService:
    def __init__(self, session, publisher, issuer_url, audience, cache_url, metrics):
        self.db = session
        self.publisher = publisher
        self.issuer_url = issuer_url
        self.audience = audience
        self.cache_url = cache_url
        self.metrics = metrics

        self._publisher_jwk_key = f"/warehouse/oidc/jwks/{self.publisher}"
        self._publisher_timeout_key = f"{self._publisher_jwk_key}/timeout"

    def _store_keyset(self, keys):
        """
        Store the given keyset for the given publisher, setting the timeout key
        in the process.
        """

        with redis.StrictRedis.from_url(self.cache_url) as r:
            r.set(self._publisher_jwk_key, json.dumps(keys))
            r.setex(self._publisher_timeout_key, 60, "placeholder")

    def _get_keyset(self):
        """
        Return the cached keyset for the given publisher, or an empty
        keyset if no keys are currently cached.
        """

        with redis.StrictRedis.from_url(self.cache_url) as r:
            keys = r.get(self._publisher_jwk_key)
            timeout = bool(r.exists(self._publisher_timeout_key))
            if keys is not None:
                return (json.loads(keys), timeout)
            else:
                return ({}, timeout)

    def _refresh_keyset(self):
        """
        Attempt to refresh the keyset from the OIDC publisher, assuming no
        timeout is in effect.

        Returns the refreshed keyset, or the cached keyset if a timeout is
        in effect.

        Returns the cached keyset on any publisher access or format errors.
        """

        # Fast path: we're in a cooldown from a previous refresh.
        keys, timeout = self._get_keyset()
        if timeout:
            self.metrics.increment(
                "warehouse.oidc.refresh_keyset.timeout",
                tags=[f"publisher:{self.publisher}"],
            )
            return keys

        oidc_url = f"{self.issuer_url}/.well-known/openid-configuration"

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
        self._store_keyset(keys)

        return keys

    def _get_key(self, key_id):
        """
        Return a JWK for the given key ID, or None if the key can't be found
        in this publisher's keyset.
        """

        keyset, _ = self._get_keyset()
        if key_id not in keyset:
            keyset = self._refresh_keyset()
        if key_id not in keyset:
            self.metrics.increment(
                "warehouse.oidc.get_key.error",
                tags=[f"publisher:{self.publisher}", f"key_id:{key_id}"],
            )
            return None
        return jwt.PyJWK(keyset[key_id])

    def _get_key_for_token(self, token):
        """
        Return a JWK suitable for verifying the given JWT.

        The JWT is not verified at this point, and this step happens
        prior to any verification.
        """
        unverified_header = jwt.get_unverified_header(token)
        return self._get_key(unverified_header["kid"])

    def verify_jwt_signature(self, unverified_token: str) -> SignedClaims | None:
        try:
            key = self._get_key_for_token(unverified_token)
        except Exception as e:
            # The user might feed us an entirely nonsense JWT, e.g. one
            # with missing components.
            self.metrics.increment(
                "warehouse.oidc.verify_jwt_signature.malformed_jwt",
                tags=[f"publisher:{self.publisher}"],
            )

            if not isinstance(e, jwt.PyJWTError):
                with sentry_sdk.push_scope() as scope:
                    scope.fingerprint = e
                    # Similar to below: Other exceptions indicate an abstraction
                    # leak, so we log them for upstream reporting.
                    sentry_sdk.capture_message(f"JWT backend raised generic error: {e}")
            return None

        try:
            # NOTE: Many of the keyword arguments here are defaults, but we
            # set them explicitly to assert the intended verification behavior.
            signed_payload = jwt.decode(
                unverified_token,
                key=key.key,
                algorithms=["RS256"],
                options=dict(
                    verify_signature=True,
                    # "require" only checks for the presence of these claims, not
                    # their validity. Each has a corresponding "verify_" kwarg
                    # that enforces their actual validity.
                    require=["iss", "iat", "nbf", "exp", "aud"],
                    verify_iss=True,
                    verify_iat=True,
                    verify_nbf=True,
                    verify_exp=True,
                    verify_aud=True,
                ),
                issuer=self.issuer_url,
                audience=self.audience,
                leeway=30,
            )
            return SignedClaims(signed_payload)
        except Exception as e:
            self.metrics.increment(
                "warehouse.oidc.verify_jwt_signature.invalid_signature",
                tags=[f"publisher:{self.publisher}"],
            )
            if not isinstance(e, jwt.PyJWTError):
                with sentry_sdk.push_scope() as scope:
                    scope.fingerprint = e
                    # We expect pyjwt to only raise subclasses of PyJWTError, but
                    # we can't enforce this. Other exceptions indicate an abstraction
                    # leak, so we log them for upstream reporting.
                    sentry_sdk.capture_message(f"JWT backend raised generic error: {e}")
            return None

    def find_publisher(
        self, signed_claims: SignedClaims, *, pending: bool = False
    ) -> OIDCPublisher | PendingOIDCPublisher | None:
        metrics_tags = [f"publisher:{self.publisher}"]
        self.metrics.increment(
            "warehouse.oidc.find_publisher.attempt",
            tags=metrics_tags,
        )

        publisher = find_publisher_by_issuer(
            self.db, self.issuer_url, signed_claims, pending=pending
        )
        if publisher is None:
            self.metrics.increment(
                "warehouse.oidc.find_publisher.publisher_not_found",
                tags=metrics_tags,
            )
            return None

        if not publisher.verify_claims(signed_claims):
            self.metrics.increment(
                "warehouse.oidc.find_publisher.invalid_claims",
                tags=metrics_tags,
            )
            return None
        else:
            self.metrics.increment(
                "warehouse.oidc.find_publisher.ok",
                tags=metrics_tags,
            )

        return publisher

    def reify_pending_publisher(self, pending_publisher, project):
        new_publisher = pending_publisher.reify(self.db)
        project.oidc_publishers.append(new_publisher)
        return new_publisher


class OIDCPublisherServiceFactory:
    def __init__(self, publisher, issuer_url, service_class=OIDCPublisherService):
        self.publisher = publisher
        self.issuer_url = issuer_url
        self.service_class = service_class

    def __call__(self, _context, request):
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

    def __eq__(self, other):
        if not isinstance(other, OIDCPublisherServiceFactory):
            return NotImplemented

        return (self.publisher, self.issuer_url, self.service_class) == (
            other.publisher,
            other.issuer_url,
            other.service_class,
        )
