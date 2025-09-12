# SPDX-License-Identifier: Apache-2.0

import alembic.command
import click

from warehouse.cli.db import db


@db.command()
@click.argument("revision", required=True)
@click.pass_obj
def stamp(config, revision, **kwargs):
    """
    Stamp the revision table with the given revision.
    """
    alembic.command.stamp(config.alembic_config(), revision, **kwargs)
