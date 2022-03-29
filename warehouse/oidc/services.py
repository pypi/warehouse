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

import jwt
import redis
import requests
import sentry_sdk

from zope.interface import implementer

from warehouse.metrics.interfaces import IMetricsService
from warehouse.oidc.interfaces import IOIDCProviderService


@implementer(IOIDCProviderService)
class OIDCProviderService:
    def __init__(self, provider, issuer_url, cache_url, metrics):
        self.provider = provider
        self.issuer_url = issuer_url
        self.cache_url = cache_url
        self.metrics = metrics

        self._provider_jwk_key = f"/warehouse/oidc/jwks/{self.provider}"
        self._provider_timeout_key = f"{self._provider_jwk_key}/timeout"

    def _store_keyset(self, keys):
        """
        Store the given keyset for the given provider, setting the timeout key
        in the process.
        """

        with redis.StrictRedis.from_url(self.cache_url) as r:
            r.set(self._provider_jwk_key, json.dumps(keys))
            r.setex(self._provider_timeout_key, 60, "placeholder")

    def _get_keyset(self):
        """
        Return the cached keyset for the given provider, or an empty
        keyset if no keys are currently cached.
        """

        with redis.StrictRedis.from_url(self.cache_url) as r:
            keys = r.get(self._provider_jwk_key)
            timeout = bool(r.exists(self._provider_timeout_key))
            if keys is not None:
                return (json.loads(keys), timeout)
            else:
                return ({}, timeout)

    def _refresh_keyset(self):
        """
        Attempt to refresh the keyset from the OIDC provider, assuming no
        timeout is in effect.

        Returns the refreshed keyset, or the cached keyset if a timeout is
        in effect.

        Returns the cached keyset on any provider access or format errors.
        """

        # Fast path: we're in a cooldown from a previous refresh.
        keys, timeout = self._get_keyset()
        if timeout:
            self.metrics.increment(
                "warehouse.oidc.refresh_keyset.timeout",
                tags=[f"provider:{self.provider}"],
            )
            return keys

        oidc_url = f"{self.issuer_url}/.well-known/openid-configuration"

        resp = requests.get(oidc_url)

        # For whatever reason, an OIDC provider's configuration URL might be
        # offline. We don't want to completely explode here, since other
        # providers might still be online (and need updating), so we spit
        # out an error and return None instead of raising.
        if not resp.ok:
            sentry_sdk.capture_message(
                f"OIDC provider {self.provider} failed to return configuration: "
                f"{oidc_url}"
            )
            return keys

        oidc_conf = resp.json()
        jwks_url = oidc_conf.get("jwks_uri")

        # A valid OIDC configuration MUST have a `jwks_uri`, but we
        # defend against its absence anyways.
        if jwks_url is None:
            sentry_sdk.capture_message(
                f"OIDC provider {self.provider} is returning malformed "
                "configuration (no jwks_uri)"
            )
            return keys

        resp = requests.get(jwks_url)

        # Same reasoning as above.
        if not resp.ok:
            sentry_sdk.capture_message(
                f"OIDC provider {self.provider} failed to return JWKS JSON: "
                f"{jwks_url}"
            )
            return keys

        jwks_conf = resp.json()
        new_keys = jwks_conf.get("keys")

        # Another sanity test: an OIDC provider should never return an empty
        # keyset, but there's nothing stopping them from doing so. We don't
        # want to cache an empty keyset just in case it's a short-lived error,
        # so we check here, error, and return the current cache instead.
        if not new_keys:
            sentry_sdk.capture_message(
                f"OIDC provider {self.provider} returned JWKS JSON but no keys"
            )
            return keys

        keys = {key["kid"]: key for key in new_keys}
        self._store_keyset(keys)

        return keys

    def get_key(self, key_id):
        """
        Return a JWK for the given key ID, or None if the key can't be found
        in this provider's keyset.
        """

        keyset, _ = self._get_keyset()
        if key_id not in keyset:
            keyset = self._refresh_keyset()
        if key_id not in keyset:
            self.metrics.increment(
                "warehouse.oidc.get_key.error",
                tags=[f"provider:{self.provider}", f"key_id:{key_id}"],
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
        return self.get_key(unverified_header["kid"])

    def verify_signature_only(self, token):
        key = self._get_key_for_token(token)

        try:
            # NOTE: Many of the keyword arguments here are defaults, but we
            # set them explicitly to assert the intended verification behavior.
            signed_payload = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
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
                issuer=self.issuer_url,
                audience="pypi",
                leeway=30,
            )
            return signed_payload
        except jwt.PyJWTError:
            return None
        except Exception as e:
            # We expect pyjwt to only raise subclasses of PyJWTError, but
            # we can't enforce this. Other exceptions indicate an abstraction
            # leak, so we log them for upstream reporting.
            sentry_sdk.capture_message(f"JWT verify raised generic error: {e}")
            return None

    def verify_for_project(self, token, project):
        signed_payload = self.verify_signature_only(token)

        metrics_tags = [f"project:{project.name}", f"provider:{self.provider}"]
        self.metrics.increment(
            "warehouse.oidc.verify_for_project.attempt",
            tags=metrics_tags,
        )

        if signed_payload is None:
            self.metrics.increment(
                "warehouse.oidc.verify_for_project.invalid_signature",
                tags=metrics_tags,
            )
            return False

        # In order for a signed JWT to be valid for a particular PyPI project,
        # it must match at least one of the OIDC providers registered to
        # the project.
        verified = any(
            provider.verify_claims(signed_payload)
            for provider in project.oidc_providers
        )
        if not verified:
            self.metrics.increment(
                "warehouse.oidc.verify_for_project.invalid_claims",
                tags=metrics_tags,
            )
        else:
            self.metrics.increment(
                "warehouse.oidc.verify_for_project.ok",
                tags=metrics_tags,
            )

        return verified


class OIDCProviderServiceFactory:
    def __init__(self, provider, issuer_url, service_class=OIDCProviderService):
        self.provider = provider
        self.issuer_url = issuer_url
        self.service_class = service_class

    def __call__(self, _context, request):
        cache_url = request.registry.settings["oidc.jwk_cache_url"]
        metrics = request.find_service(IMetricsService, context=None)

        return self.service_class(self.provider, self.issuer_url, cache_url, metrics)

    def __eq__(self, other):
        if not isinstance(other, OIDCProviderServiceFactory):
            return NotImplemented

        return (self.provider, self.issuer_url, self.service_class) == (
            other.provider,
            other.issuer_url,
            other.service_class,
        )
