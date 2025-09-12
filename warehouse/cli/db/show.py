# SPDX-License-Identifier: Apache-2.0

import alembic.command
import click

from warehouse.cli.db import db


@db.command()
@click.argument("revision", required=True)
@click.pass_obj
def show(config, revision, **kwargs):
    """
    Show the revision(s) denoted by the given symbol.
    """
    alembic.command.show(config.alembic_config(), revision, **kwargs)
