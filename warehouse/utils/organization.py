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

from pyramid.httpexceptions import HTTPSeeOther


def confirm_organization(
    organization,
    request,
    fail_route,
    field_name="confirm_organization_name",
    error_message="Could not delete organization",
):
    confirm = request.POST.get(field_name, "").strip()
    if not confirm:
        request.session.flash("Confirm the request", queue="error")
        raise HTTPSeeOther(
            request.route_path(
                fail_route,
                organization_name=organization.normalized_name,
            )
        )

    organization_name = organization.name.strip()
    if confirm != organization_name:
        request.session.flash(
            f"{error_message} - {confirm!r} is not the same as {organization_name!r}",
            queue="error",
        )
        raise HTTPSeeOther(
            request.route_path(
                fail_route,
                organization_name=organization.normalized_name,
            )
        )


def confirm_team(
    team,
    request,
    fail_route,
    field_name="confirm_team_name",
    error_message="Could not delete team",
):
    confirm = request.POST.get(field_name, "").strip()
    if not confirm:
        request.session.flash("Confirm the request", queue="error")
        raise HTTPSeeOther(
            request.route_path(
                fail_route,
                organization_name=team.organization.normalized_name,
                team_name=team.normalized_name,
            )
        )

    team_name = team.name.strip()
    if confirm != team_name:
        request.session.flash(
            f"{error_message} - {confirm!r} is not the same as {team_name!r}",
            queue="error",
        )
        raise HTTPSeeOther(
            request.route_path(
                fail_route,
                organization_name=team.organization.normalized_name,
                team_name=team.normalized_name,
            )
        )
