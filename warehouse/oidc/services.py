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
import logging

import redis
import requests

from jwt import PyJWK
from zope.interface import implementer

from warehouse.oidc.interfaces import IJWKService
from warehouse.utils import oidc

logger = logging.getLogger(__name__)


@implementer(IJWKService)
class JWKService:
    def __init__(self, config):
        self._cache_url = config.registry.settings.get("oidc.jwk_cache_url")

    @classmethod
    def create_service(cls, _context, config):
        return cls(config)

    def _provider_jwk_key(self, provider):
        """
        Returns a reasonable Redis key for storing JWKs for the given provider.
        """
        return f"/warehouse/oidc/jwks/{provider}"

    def _provider_timeout_key(self, provider):
        """
        Returns a reasonable Redis key for storing the "timeout" flag for the
        given provider, indicating whether we should attempt to refresh the
        keyset.
        """
        # NOTE: We could use a TTL on the actual Redis key for the keyset,
        # but only once Warehouse upgrades to Redis >= 6.0.
        return f"{self._provider_jwk_key(provider)}/timeout"

    def _store_keyset(self, provider, keys):
        """
        Store the given keyset for the given provider, setting the timeout key
        in the process.
        """
        with redis.StrictRedis.from_url(self._cache_url) as r:
            r.set(self._provider_jwk_key(provider), json.dumps(keys))
            r.setex(self._provider_timeout_key(provider), 60, "placeholder")

    def _get_keyset(self, provider):
        """
        Return the cached keyset for the given provider, if it exists,
        along with the timeout state.
        """
        with redis.StrictRedis.from_url(self._cache_url) as r:
            keys = r.get(self._provider_jwk_key(provider))
            timeout = bool(r.exists(self._provider_timeout_key(provider)))
            if keys is not None:
                return (json.loads(keys), timeout)
            else:
                return (None, timeout)

    def _fetch_keyset(self, provider):
        oidc_url = f"{oidc.OIDC_PROVIDERS[provider]}/{oidc.WELL_KNOWN_OIDC_CONF}"

        resp = requests.get(oidc_url)

        # For whatever reason, an OIDC provider's configuration URL might be
        # offline. We don't want to completely explode here, since other
        # providers might still be online (and need updating), so we spit
        # out an error and return None instead of raising.
        if not resp.ok:
            logger.error(
                f"error querying OIDC configuration for {provider}: {oidc_url}"
            )
            return None

        oidc_conf = resp.json()
        jwks_url = oidc_conf["jwks_uri"]

        resp = requests.get(jwks_url)

        # Same reasoning as above.
        if not resp.ok:
            logger.error(f"error querying JWKS JSON for {provider}: {jwks_url}")
            return None

        jwks_conf = resp.json()
        keys = jwks_conf["keys"]

        # Another sanity test: an OIDC provider should never return an empty
        # keyset, but there's nothing stopping them from doing so. We don't
        # want to cache an empty keyset just in case it's a short-lived error,
        # so we check here, error, and return None instead.
        if len(keys) == 0:
            logger.error(f"{provider} returned JWKS conf but no keys")
            return None

        return keys

    def get_key(self, provider, key_id):
        # The key retrieval logic is as follows:
        # 1. Check the Redis store for the provider's keyset.
        # 2. If the keyset is not present, try to retrieve it
        #    (fetch on first use).
        # 3. Search the keyset for a key matching the key ID.
        # 4. If we have a match, return the corresponding key.
        # 5. If there's no match and we're in a timeout, return None.
        # 6. Otherwise, try to update the keyset and match the key ID again.
        #
        # In this scheme, we perform:
        # * No fetches in the happy case (keyset is already updated)
        # * One fetch in the FOFU case (keyset doesn't exist yet)
        # * One fetch in the sad case (keyset is stale and needs to be updated)
        # * Two fetches in the pathological case (FOFU returns nothing + sad)
        #
        # The pathological case should almost never happen (it requires
        # the OIDC provider to have a JWKS serving bug on their end), so we
        # don't attempt to optimize for avoiding it. We also don't subject
        # it to the timeout restrictions, since we want to cache the actual
        # keyset when it becomes available again ASAP.

        (keys, timeout) = self._get_keyset(provider)

        if keys is None:
            # FOFU case: no keys means that we're either starting from scratch
            # or the OIDC provider returned an empty keyset, which is an error
            # on the provider's side.

            # If we don't have any keys and we're in an active timeout, return None.
            if timeout:
                logger.warning(f"no keys for {provider} during active timeout")
                return None

            keys = self._fetch_keyset(provider)

            # `None` indicates an error on the OIDC provider's side, which
            # we don't want to cache or timeout against.
            if keys is None:
                return None

            # Update the keyset for future retrieval.
            self._store_keyset(provider, keys)

        # If we do have keys, then check them against the given key ID.
        key = next((k for k in keys if k["kid"] == key_id), None)

        if key is not None:
            # Happy case: we already have the key.
            return PyJWK(key)
        elif key is None and timeout:
            logger.warning(f"no keys match {key_id} during active timeout")
            # Sad case: we don't have the key, and a timeout is pending
            # from the last keyset fetch.
            return None
        else:
            # Maybe case: we don't have the key, but the keyset might have
            # changed since we last checked. Perform the same updates as
            # the FOFU case above.
            keys = self._fetch_keyset(provider)

            # `None` indicates an error on the OIDC provider's side, which
            # we don't want to cache or timeout against.
            if keys is None:
                return None

            self._store_keyset(provider, keys)

            return next((PyJWK(k) for k in keys if k["kid"] == key_id), None)
