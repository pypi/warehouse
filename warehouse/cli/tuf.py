# SPDX-License-Identifier: Apache-2.0

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
