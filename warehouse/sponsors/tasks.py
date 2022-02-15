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
    protocol = "https"
    if "localhost" in host:
        protocol = "http"

    qs = urlencode({"publisher": "pypi", "flight": "sponsors"})
    url = f"{protocol}://{host}/api/v2/sponsors/logo-placement/?{qs}"
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    for sponsor_info in response.json():
        sponsor = Sponsor(
            name=sponsor_info["sponsor"],
            slug=sponsor_info["sponsor_slug"],
            service=sponsor_info["description"], # activity markdown??????
            link_url=sponsor_info["sponsor_url"],
            color_logo_url=sponsor_info["logo"],
            level_name=sponsor_info["level_name"],
            level_order=sponsor_info["level_order"],
            is_active=True,
            psf_sponsor=True,
            origin="remote",
        )
        request.db.add(sponsor)

    request.db.commit()
