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

import click

from warehouse.cli import warehouse


@warehouse.group()  # pragma: no branch
def oidc():
    """
    Manage the Warehouse OIDC components.
    """


@oidc.command()
@click.pass_obj
@click.argument("provider")
def prime_provider(config, provider):
    """
    Update Warehouse's JWK sets for the given provider.
    """

    from warehouse.oidc.services import JWKService

    jwk_service = JWKService.create_service(None, config)

    # "cachebuster" is not a real ID; we use it to force a refresh.
    jwk_service.get_key(provider, "cachebuster")


@oidc.command()
@click.pass_obj
@click.argument("provider")
@click.argument("key-id")
def get_key(config, provider, key_id):
    """
    Return the JWK for the given provider's key ID.
    """

    from warehouse.oidc.services import JWKService

    jwk_service = JWKService.create_service(None, config)

    key = jwk_service.get_key(provider, key_id)
    print(json.dumps(key._jwk_data))
