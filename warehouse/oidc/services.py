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

from zope.interface import implementer

from warehouse.oidc.interfaces import IJWKService
from warehouse.utils import oidc

logger = logging.getLogger(__name__)


@implementer(IJWKService)
class JWKService:
    def __init__(self, config):
        self._config = config

    @classmethod
    def create_service(cls, _context, config):
        return cls(config)

    def fetch_keysets(self):
        for provider, oidc_url in oidc.OIDC_PROVIDERS.items():
            # OIDC_PROVIDERS provides the issuer URL, which needs to be
            # built up to reach the actual configuration.
            oidc_url = f"{oidc_url}/{oidc.WELL_KNOWN_OIDC_CONF}"

            resp = requests.get(oidc_url)

            # For whatever reason, an OIDC provider's configuration URL might be
            # offline. We don't want to completely explode here, since other
            # providers might still be online (and need updating), so we spit
            # out an error and continue instead of raising.
            if not resp.ok:
                logger.error(
                    f"error querying OIDC configuration for {provider}: {oidc_url}"
                )
                continue

            oidc_conf = resp.json()
            jwks_url = oidc_conf["jwks_uri"]

            resp = requests.get(jwks_url)

            # Same reasoning as above.
            if not resp.ok:
                logger.error(f"error querying JWKS JSON for {provider}: {jwks_url}")
                continue

            jwks_conf = resp.json()
            keys = jwks_conf["keys"]

            yield (provider, keys)

    def keyset_for_provider(self, provider):
        with redis.StrictRedis.from_url(
            self._config.registry.settings.get("oidc.jwk_cache_url")
        ) as r:
            return json.loads(r.get(oidc.jwk_cache_key(provider)))
