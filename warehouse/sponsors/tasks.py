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
from urllib.parse import urlencode

import requests

from sqlalchemy import or_, true
from sqlalchemy.exc import NoResultFound

from warehouse import tasks
from warehouse.sponsors.models import Sponsor


@tasks.task(ignore_result=True, acks_late=True)
def update_pypi_sponsors(request):
    """
    Read data from pythondotorg's logo placement API and update Sponsors
    table to mirror it.
    """
    host = request.registry.settings["pythondotorg.host"]
    token = request.registry.settings["pythondotorg.api_token"]
    headers = {"Authorization": f"Token {token}"}

    qs = urlencode({"publisher": "pypi", "flight": "sponsors"})
    url = f"{host}/api/v2/sponsors/logo-placement/?{qs}"
    response = requests.get(url, headers=headers, timeout=5)
    response.raise_for_status()

    # deactivate current PSF sponsors to keep it up to date with API
    request.db.query(Sponsor).filter(Sponsor.psf_sponsor == true()).update(
        {"psf_sponsor": False}
    )

    for sponsor_info in response.json():
        name = sponsor_info["sponsor"]
        slug = sponsor_info["sponsor_slug"]
        query = request.db.query(Sponsor)
        try:
            sponsor = query.filter(
                or_(Sponsor.name == name, Sponsor.slug == slug)
            ).one()
            if sponsor.infra_sponsor or sponsor.one_time:
                continue
        except NoResultFound:
            sponsor = Sponsor()
            request.db.add(sponsor)

        sponsor.name = name
        sponsor.slug = slug
        sponsor.service = sponsor_info["description"]
        sponsor.link_url = sponsor_info["sponsor_url"]
        sponsor.color_logo_url = sponsor_info["logo"]
        sponsor.level_name = sponsor_info["level_name"]
        sponsor.level_order = sponsor_info["level_order"]
        sponsor.is_active = True
        sponsor.psf_sponsor = True
        sponsor.origin = "remote"
