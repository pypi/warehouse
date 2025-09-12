# SPDX-License-Identifier: Apache-2.0

import alembic.command
import click

from warehouse.cli.db import db


@db.command()
@click.argument("revision", required=True)
@click.option(
    "--sql", is_flag=True, help="Generate SQL script instead of applying the upgrade."
)
@click.pass_obj
def upgrade(config, revision, sql, **kwargs):
    """
    Upgrade database.
    """
    alembic.command.upgrade(config.alembic_config(), revision, sql=sql, **kwargs)
