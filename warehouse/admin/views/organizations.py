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

from pyramid.httpexceptions import HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config

from warehouse.accounts.interfaces import IUserService
from warehouse.email import (
    send_admin_new_organization_approved_email,
    send_admin_new_organization_declined_email,
    send_new_organization_approved_email,
    send_new_organization_declined_email,
)
from warehouse.organizations.interfaces import IOrganizationService


@view_config(
    route_name="admin.organization.detail",
    require_methods=False,
    renderer="admin/organizations/detail.html",
    permission="admin",
    has_translations=True,
    uses_session=True,
    require_csrf=True,
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
        "organization": organization,
        "user": user,
    }


@view_config(
    route_name="admin.organization.approve",
    require_methods=["POST"],
    renderer="admin/organizations/approve.html",
    permission="admin",
    has_translations=True,
    uses_session=True,
    require_csrf=True,
    require_reauth=True,
)
def approve(request):
    organization_service = request.find_service(IOrganizationService, context=None)
    user_service = request.find_service(IUserService, context=None)

    organization_id = request.matchdict["organization_id"]
    organization = organization_service.get_organization(organization_id)
    if organization is None:
        raise HTTPNotFound
    elif organization.name != request.params.get("organization_name"):
        request.session.flash("Wrong confirmation input", queue="error")
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    # TODO: More robust way to get requesting user
    user = organization.users[0]

    message = request.params.get("message", "")

    organization_service.approve_organization(organization.id)
    organization_service.record_event(
        organization.id,
        tag="organization:approve",
        additional={"approved_by": request.user.username},
    )
    send_admin_new_organization_approved_email(
        request,
        user_service.get_admins(),
        organization_name=organization.name,
        initiator_username=user.username,
        message=message,
    )
    send_new_organization_approved_email(
        request,
        user,
        organization_name=organization.name,
        message=message,
    )
    request.session.flash(
        f'Request for "{organization.name}" organization approved', queue="success"
    )

    return HTTPSeeOther(
        request.route_path("admin.organization.detail", organization_id=organization.id)
    )


@view_config(
    route_name="admin.organization.decline",
    require_methods=["POST"],
    renderer="admin/organizations/decline.html",
    permission="admin",
    has_translations=True,
    uses_session=True,
    require_csrf=True,
    require_reauth=True,
)
def decline(request):
    organization_service = request.find_service(IOrganizationService, context=None)
    user_service = request.find_service(IUserService, context=None)

    organization_id = request.matchdict["organization_id"]
    organization = organization_service.get_organization(organization_id)
    if organization is None:
        raise HTTPNotFound
    elif organization.name != request.params.get("organization_name"):
        request.session.flash("Wrong confirmation input", queue="error")
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    # TODO: More robust way to get requesting user
    user = organization.users[0]

    message = request.params.get("message", "")

    organization_service.decline_organization(organization.id)
    organization_service.record_event(
        organization.id,
        tag="organization:decline",
        additional={"declined_by": request.user.username},
    )
    send_admin_new_organization_declined_email(
        request,
        user_service.get_admins(),
        organization_name=organization.name,
        initiator_username=user.username,
        message=message,
    )
    send_new_organization_declined_email(
        request,
        user,
        organization_name=organization.name,
        message=message,
    )
    request.session.flash(
        f'Request for "{organization.name}" organization declined', queue="success"
    )

    return HTTPSeeOther(
        request.route_path("admin.organization.detail", organization_id=organization.id)
    )
