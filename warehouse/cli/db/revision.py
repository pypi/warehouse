# SPDX-License-Identifier: Apache-2.0

import alembic.command
import click

from warehouse.cli.db import db


@db.command()
@click.option(
    "--message", "-m", metavar="MESSAGE", help="Message string to use with the revision"
)
@click.option(
    "--autogenerate",
    "-a",
    is_flag=True,
    help=(
        "Populate revision script with candidate migration operations, based "
        "on comparison of database to tables."
    ),
)
@click.option(
    "--head",
    metavar="HEAD",
    help=("Specify a head revision or <brachname>@head to base new revision on."),
)
@click.option(
    "--splice",
    is_flag=True,
    help="Allow a non-head revision as the 'head' to splice onto.",
)
@click.option(
    "--branch-label",
    metavar="BRANCH",
    help="Specify a branch label to apply to the new revision.",
)
@click.pass_obj
def revision(config, **kwargs):
    """
    Create a new revision file.
    """
    alembic.command.revision(config.alembic_config(), **kwargs)
