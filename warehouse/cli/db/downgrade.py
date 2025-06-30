# SPDX-License-Identifier: Apache-2.0

import alembic.command
import click

from warehouse.cli.db import db


@db.command()
@click.argument("revision", required=True)
@click.pass_obj
def downgrade(config, revision, **kwargs):
    """
    Revert to a previous version.
    """
    alembic.command.downgrade(config.alembic_config(), revision, **kwargs)
