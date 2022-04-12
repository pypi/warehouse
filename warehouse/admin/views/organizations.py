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

from pyramid.view import view_config


@view_config(
    route_name="admin.organization.approve",
    renderer="admin/organizations/approve.html",
    permission="admin",
    require_methods=False,
    uses_session=True,
    has_translations=True,
)
def approve(request):
    return {
        "username": "example",
        "user_full_name": "Example",
        "user_email": "webmaster@example.com",
        "organization_name": "example",
        "organization_display_name": "Example",
        "organization_url": "https://www.example.com/",
        "organization_description": "This company is for use in illustrative examples in documents. You may use this company in literature without prior coordination or asking for permission.",
        "organization_type": "Company",
    }
