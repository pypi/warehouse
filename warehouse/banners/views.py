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

import datetime

from pyramid.view import view_config

from warehouse.banners.models import Banner


@view_config(
    route_name="includes.db-banners",
    renderer="includes/banner-messages.html",
    uses_session=True,
    has_translations=True,
)
def list_banner_messages(request):
    # used to preview specific banner
    banner_id = request.params.get("single_banner")
    if banner_id:
        query = request.db.query(Banner).filter(Banner.id == banner_id)
    else:
        today = datetime.date.today()
        query = request.db.query(Banner).filter(
            (Banner.active == True) & (Banner.end >= today)  # noqa
        )

    return {"banners": query.all()}
