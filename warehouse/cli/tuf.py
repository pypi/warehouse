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

from tuf import repository_tool

from warehouse.cli import warehouse
from warehouse.tuf.tasks import new_repo as _new_repo


@warehouse.group()  # pragma: no-branch
def tuf():
    """
    Manage Warehouse's TUF state.
    """


# TODO: Need subcommands for:
# 1. creating the world (totally new TUF repo, including root)
# 2. updating the root metadata (including revocations?)
# 3. removing stale metadata


@tuf.command()
@click.pass_obj
@click.option("--name", "name_", help="The name of the TUF role for this keypair")
@click.option("--path", "path_", help="The basename of the Ed25519 keypair to generate")
def keypair(config, name_, path_):
    repository_tool.generate_and_write_ed25519_keypair(
        path_, password=config.registry.settings[f"tuf.{name_}.secret"]
    )


@tuf.command()
@click.pass_obj
def new_repo(config):
    """
    Initialize the TUF repository from scratch, including a brand new root.
    """

    request = config.task(_new_repo).get_request()
    config.task(_new_repo).run(request)


@tuf.command()
@click.pass_obj
def new_root(config):
    """
    Create a new
    """
    pass
