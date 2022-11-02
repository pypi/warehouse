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

from warehouse.oidc.interfaces import IOIDCProviderService
from warehouse.oidc.services import OIDCProviderServiceFactory
from warehouse.oidc.utils import GITHUB_OIDC_ISSUER_URL


def includeme(config):
    oidc_provider_service_class = config.maybe_dotted(
        config.registry.settings["oidc.backend"]
    )

    config.register_service_factory(
        OIDCProviderServiceFactory(
            provider="github",
            issuer_url=GITHUB_OIDC_ISSUER_URL,
            service_class=oidc_provider_service_class,
        ),
        IOIDCProviderService,
        name="github",
    )

    # During deployments, we separate auth routes into their own subdomain
    # to simplify caching exclusion.
    auth = config.get_settings().get("auth.domain")

    config.add_route("oidc.mint_token", "/_/oidc/github/mint-token", domain=auth)
