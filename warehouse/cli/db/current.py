# SPDX-License-Identifier: Apache-2.0

import alembic.command
import click

from warehouse.cli.db import db


@db.command()
@click.pass_obj
def current(config, **kwargs):
    """
    Display the current revision for a database.
    """
    alembic.command.current(config.alembic_config(), **kwargs)
