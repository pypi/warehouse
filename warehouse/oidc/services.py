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

import redis
import requests
import sentry_sdk

from jwt import PyJWK
from zope.interface import implementer

from warehouse.metrics.interfaces import IMetricsService
from warehouse.oidc.interfaces import IJWKService
from warehouse.utils import oidc


@implementer(IJWKService)
class JWKService:
    def __init__(self, provider, cache_url, metrics):
        self.provider
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
            self.metrics.increment("warehouse.oidc.refresh_keyset.timeout")
            return keys

        oidc_url = f"{oidc.OIDC_PROVIDERS[self.provider]}/{oidc.WELL_KNOWN_OIDC_CONF}"

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
        keys = jwks_conf.get("keys")

        # Another sanity test: an OIDC provider should never return an empty
        # keyset, but there's nothing stopping them from doing so. We don't
        # want to cache an empty keyset just in case it's a short-lived error,
        # so we check here, error, and return the current cache instead.
        if not keys:
            sentry_sdk.capture_message(
                f"OIDC provider {self.provider} returned JWKS but no keys"
            )
            return keys

        keys = {key["kid"]: key for key in keys}
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
                "warehouse.oidc.get_key.error", tags=[f"key_id:{key_id}"]
            )
            return None
        return PyJWK(keyset[key_id])


class JWKServiceFactory:
    def __init__(self, provider, service_class=JWKService):
        self.provider = provider
        self.service_class = service_class

    def __call__(self, _context, request):
        cache_url = request.registry.settings["oidc.jwk_cache_url"]
        metrics = request.find_service(IMetricsService, context=None)

        return self.service_class(self.provider, cache_url, metrics)

    def __eq__(self, other):
        if not isinstance(other, JWKServiceFactory):
            return NotImplemented

        return (self.provider, self.service_class) == (
            other.provider,
            other.service_class,
        )
