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
@click.argument("key-id")
def get_key(config, provider, key_id):
    """
    Return the JWK for the given provider's key ID.
    """

    from warehouse.oidc.services import JWKService

    cache_url = config.registry.settings["oidc.jwk_cache_url"]
    jwk_service = JWKService(provider, cache_url)

    key = jwk_service.get_key(provider, key_id)
    print(json.dumps(key._jwk_data))
