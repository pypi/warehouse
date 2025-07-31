# SPDX-License-Identifier: Apache-2.0

import alembic.command
import click

from warehouse.cli.db import db


@db.command()
@click.option(
    "--message", "-m", metavar="MESSAGE", help="Message string to use with the revision"
)
@click.option(
    "--branch-label",
    metavar="BRANCH",
    help="Specify a branch label to apply to the new revision.",
)
@click.argument("revisions", nargs=-1, required=True)
@click.pass_obj
def merge(config, revisions, **kwargs):
    """
    Merge one or more revisions.

    Takes one or more revisions or "heads" for all heads and merges them into
    a single revision.
    """
    alembic.command.merge(config.alembic_config(), revisions, **kwargs)
