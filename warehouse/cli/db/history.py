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

from warehouse.cli.db import db


@db.command()
@click.argument("revision_range", required=True)
@click.pass_obj
def history(config, revision_range, **kwargs):
    """
    List changeset scripts in chronological order.
    """
    alembic.command.history(config.alembic_config(), revision_range, **kwargs)
