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

from pyramid.httpexceptions import HTTPNotFound
from pyramid.view import view_config

from warehouse.organizations.interfaces import IOrganizationService


@view_config(
    route_name="admin.organization.detail",
    renderer="admin/organizations/detail.html",
    permission="admin",
    has_translations=True,
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    require_reauth=True,
)
def detail(request):
    organization_service = request.find_service(IOrganizationService, context=None)
    organization_id = request.matchdict["organization_id"]
    organization = organization_service.get_organization(organization_id)
    if organization is None:
        raise HTTPNotFound

    # TODO: More robust way to get requesting user
    user = organization.users[0]

    return {
        "username": user.username,
        "user_full_name": user.name,
        "user_email": user.public_email,
        "organization_name": organization.name,
        "organization_display_name": organization.display_name,
        "organization_link_url": organization.link_url,
        "organization_description": organization.description,
        "organization_orgtype": organization.orgtype.name,
    }
