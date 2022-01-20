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

import click

from warehouse.cli import warehouse
from warehouse.oidc.tasks import update_oidc_jwks as _update_oidc_jwks


@warehouse.group()  # pragma: no branch
def oidc():
    """
    Manage the Warehouse OIDC components.
    """


@oidc.command()
@click.pass_obj
def update_oidc_jwks(config):
    """
    Update Warehouse's JWK sets for all known OIDC providers.
    """

    request = config.task(_update_oidc_jwks).get_request()
    config.task(_update_oidc_jwks).run(request)


@oidc.command()
@click.pass_obj
@click.option(
    "--provider", "provider_", help="the name of the provider to list JWKs for"
)
def list_jwks(config, provider_):
    """
    Dump a JSON blob of all JWK sets known to Warehouse for the given provider
    """

    from warehouse.oidc.services import JWKService

    jwk_service = JWKService.create_service(None, config)

    print(jwk_service.keyset_for_provider(provider_))
