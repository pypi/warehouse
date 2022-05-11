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

from packaging.utils import canonicalize_name
from pyramid.httpexceptions import HTTPSeeOther


def confirm_organization(
    organization,
    request,
    fail_route,
    field_name="confirm_organization_name",
    error_message="Could not delete organization",
):
    confirm = request.POST.get(field_name)
    organization_name = organization.normalized_name
    if not confirm:
        request.session.flash("Confirm the request", queue="error")
        raise HTTPSeeOther(
            request.route_path(fail_route, organization_name=organization_name)
        )
    if canonicalize_name(confirm) != organization.normalized_name:
        request.session.flash(
            (
                f"{error_message} - "
                f"{confirm!r} is not the same as {organization.normalized_name!r}"
            ),
            queue="error",
        )
        raise HTTPSeeOther(
            request.route_path(fail_route, organization_name=organization_name)
        )
