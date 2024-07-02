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
from warehouse.tuf import post_bootstrap, wait_for_success


@warehouse.group()
def tuf():
    """Manage TUF."""


@tuf.command()
@click.argument("payload", type=click.File("rb", lazy=True), required=True)
@click.option("--api-server", required=True)
def bootstrap(payload, api_server):
    """Use payload file to bootstrap RSTUF server."""
    task_id = post_bootstrap(api_server, json.load(payload))
    wait_for_success(api_server, task_id)
    print(f"Bootstrap completed using `{payload.name}`. 🔐 🎉")
