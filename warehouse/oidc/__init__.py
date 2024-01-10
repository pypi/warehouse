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

from celery.schedules import crontab

from warehouse.oidc.interfaces import IOIDCPublisherService
from warehouse.oidc.services import OIDCPublisherServiceFactory
from warehouse.oidc.tasks import compute_oidc_metrics
from warehouse.oidc.utils import GITHUB_OIDC_ISSUER_URL, GOOGLE_OIDC_ISSUER_URL


def includeme(config):
    oidc_publisher_service_class = config.maybe_dotted(
        config.registry.settings["oidc.backend"]
    )

    config.register_service_factory(
        OIDCPublisherServiceFactory(
            publisher="github",
            issuer_url=GITHUB_OIDC_ISSUER_URL,
            service_class=oidc_publisher_service_class,
        ),
        IOIDCPublisherService,
        name="github",
    )
    config.register_service_factory(
        OIDCPublisherServiceFactory(
            publisher="google",
            issuer_url=GOOGLE_OIDC_ISSUER_URL,
            service_class=oidc_publisher_service_class,
        ),
        IOIDCPublisherService,
        name="google",
    )

    # During deployments, we separate auth routes into their own subdomain
    # to simplify caching exclusion.
    auth = config.get_settings().get("auth.domain")

    config.add_route("oidc.audience", "/_/oidc/audience", domain=auth)
    config.add_route("oidc.mint_token", "/_/oidc/mint-token", domain=auth)
    # NOTE: This is a legacy route for the above. Pyramid requires route
    # names to be unique, so we can't deduplicate it.
    config.add_route("oidc.github.mint_token", "/_/oidc/github/mint-token", domain=auth)

    # Compute OIDC metrics periodically
    config.add_periodic_task(crontab(minute=0, hour="*"), compute_oidc_metrics)
