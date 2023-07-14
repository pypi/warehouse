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
from warehouse.packaging.tasks import send_pep_715_notices


@warehouse.group()  # pragma: no branch
def projects():
    """
    Group for projects commands.
    """


@projects.command()
@click.pass_obj
def notify_pep_715(config):
    """
    Notifies projects that have uploaded eggs since Jan 1, 2023 of PEP 715
    """
    request = config.task(send_pep_715_notices).get_request()
    config.task(send_pep_715_notices).run(request)
