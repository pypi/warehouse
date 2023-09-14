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

import click

from warehouse.cli import warehouse
from warehouse.packaging.tasks import (
    reconcile_file_storages as _reconcile_file_storages,
)


@warehouse.group()
def storages():
    """
    Manage the Warehouse Storages.
    """


@storages.command()
@click.pass_obj
@click.option("--batch-size", type=int, default=1)
def reconcile(config, batch_size):
    """
    Run the storage reconciliation task as a one-off
    """

    request = config.task(_reconcile_file_storages).get_request()
    request.registry.settings["reconcile_file_storages.batch_size"] = batch_size
    config.task(_reconcile_file_storages).run(request)
