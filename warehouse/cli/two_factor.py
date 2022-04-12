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
    compute_2fa_mandate as _compute_2fa_mandate,
    load_promo_codes as _load_promo_codes,
)


@warehouse.command()
@click.argument("project_names", nargs=-1)
@click.pass_obj
def compute_2fa_mandate(config, project_names):
    """
    Run a one-off computation of the 2FA-mandated projects
    """

    request = config.task(_compute_2fa_mandate).get_request()
    config.task(_compute_2fa_mandate).run(request, project_names)


@warehouse.command()
@click.argument("promofile", type=click.File("r"))
@click.pass_obj
def load_promo_codes(config, promofile):
    """
    Load promo codes into the database
    """
    codes = promofile.read().splitlines()
    request = config.task(_load_promo_codes).get_request()
    config.task(_load_promo_codes).run(request, codes)
