# SPDX-License-Identifier: Apache-2.0

import alembic.command
import click

from warehouse.cli.db import db


@db.command()
@click.argument("revision_range", required=True)
@click.pass_obj
def history(config, revision_range, **kwargs):
    """
    List changeset scripts in chronological order.
    """
    alembic.command.history(config.alembic_config(), revision_range, **kwargs)
