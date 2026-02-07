# SPDX-License-Identifier: Apache-2.0

import alembic.command
import click

from warehouse.cli.db import db


@db.command()
@click.pass_obj
def check(config):
    """
    Check if autogenerate will create new operations.
    """
    alembic.command.check(config.alembic_config())
