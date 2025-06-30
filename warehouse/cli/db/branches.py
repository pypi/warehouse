# SPDX-License-Identifier: Apache-2.0

import alembic.command
import click

from warehouse.cli.db import db


@db.command()
@click.pass_obj
def branches(config, **kwargs):
    """
    Show current branch points.
    """
    alembic.command.branches(config.alembic_config(), **kwargs)
