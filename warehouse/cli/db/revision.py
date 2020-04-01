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

from warehouse.cli.db import alembic_lock, db


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
    with alembic_lock(
        config.registry["sqlalchemy.engine"], config.alembic_config()
    ) as alembic_config:
        alembic.command.revision(alembic_config, **kwargs)
