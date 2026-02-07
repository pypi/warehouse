# SPDX-License-Identifier: Apache-2.0

import alembic.command
import click

from warehouse.cli.db import db


@db.command()
@click.option(
    "--resolve-dependencies",
    "-r",
    is_flag=True,
    help="Treat dependency versions as down revisions",
)
@click.pass_obj
def heads(config, **kwargs):
    """
    Show current available heads.
    """
    alembic.command.heads(config.alembic_config(), **kwargs)
