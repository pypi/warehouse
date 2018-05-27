# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import alembic.command
import click

from warehouse.cli.db import db, alembic_lock


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
    with alembic_lock(
        config.registry["sqlalchemy.engine"], config.alembic_config()
    ) as alembic_config:
        alembic.command.merge(alembic_config, revisions, **kwargs)
