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
import hvac

from warehouse.cli import warehouse


def _vault(config):
    return hvac.Client(
        url=config.registry.settings["vault.url"],
        token=config.registry.settings["vault.token"],
        # TODO: cert, verify
    )


@warehouse.group()
def tuf():  # pragma: no branch
    """
    Manage Warehouse's TUF state.
    """


@tuf.command()
@click.pass_obj
@click.option(
    "--rolename", required=True, help="The name of the TUF role for this keypair"
)
def keypair(config, rolename):
    """
    Generate a new TUF keypair.
    """
    vault = _vault(config)
    resp = vault.secrets.transit.create_key(
        name=rolename, exportable=False, key_type="ed25519"
    )
    resp.raise_for_status()
    info = vault.secrets.transit.read_key(name=rolename)
    print(info)
