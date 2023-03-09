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

from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound
from pyramid.view import view_config

from warehouse.cache.origin import origin_cache
from warehouse.organizations.models import Organization


@view_config(
    route_name="organizations.profile",
    context=Organization,
    renderer="organizations/profile.html",
    decorator=[
        origin_cache(1 * 24 * 60 * 60, stale_if_error=1 * 24 * 60 * 60)  # 1 day each.
    ],
    has_translations=True,
)
def profile(organization, request):
    if organization.name != request.matchdict.get("organization", organization.name):
        return HTTPMovedPermanently(
            request.current_route_path(organization=organization.name)
        )

    if organization.is_active:
        return {"organization": organization}
    raise HTTPNotFound()
