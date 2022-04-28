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

import shlex

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy import or_

from warehouse.accounts.interfaces import IUserService
from warehouse.admin.flags import AdminFlagValue
from warehouse.email import (
    send_admin_new_organization_approved_email,
    send_admin_new_organization_declined_email,
    send_new_organization_approved_email,
    send_new_organization_declined_email,
)
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import Organization
from warehouse.utils.paginate import paginate_url_factory


@view_config(
    route_name="admin.organization.list",
    renderer="admin/organizations/list.html",
    permission="moderator",
    uses_session=True,
)
def organization_list(request):
    if request.flags.enabled(AdminFlagValue.DISABLE_ORGANIZATIONS):
        raise HTTPNotFound

    q = request.params.get("q")

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    organizations_query = request.db.query(Organization).order_by(
        Organization.normalized_name
    )

    if q:
        terms = shlex.split(q)

        filters = []
        for term in terms:
            filters.append(Organization.name.ilike(term))
            filters.append(Organization.normalized_name.ilike(term))
            filters.append(Organization.display_name.ilike(term))
            filters.append(Organization.link_url.ilike(term))
            filters.append(Organization.description.ilike(term))

        organizations_query = organizations_query.filter(or_(*filters))

    organizations = SQLAlchemyORMPage(
        organizations_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {"organizations": organizations, "query": q}


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
    if request.flags.enabled(AdminFlagValue.DISABLE_ORGANIZATIONS):
        raise HTTPNotFound

    organization_service = request.find_service(IOrganizationService, context=None)
    user_service = request.find_service(IUserService, context=None)

    organization_id = request.matchdict["organization_id"]
    organization = organization_service.get_organization(organization_id)
    if organization is None:
        raise HTTPNotFound

    create_event = (
        organization.events.filter(Organization.Event.tag == "organization:create")
        .order_by(Organization.Event.time.desc())
        .first()
    )
    user = user_service.get_user(create_event.additional["created_by_user_id"])

    if organization.is_approved is True:
        approve_event = (
            organization.events.filter(Organization.Event.tag == "organization:approve")
            .order_by(Organization.Event.time.desc())
            .first()
        )
        admin = user_service.get_user(approve_event.additional["approved_by_user_id"])
    elif organization.is_approved is False:
        decline_event = (
            organization.events.filter(Organization.Event.tag == "organization:decline")
            .order_by(Organization.Event.time.desc())
            .first()
        )
        admin = user_service.get_user(decline_event.additional["declined_by_user_id"])
    else:
        admin = None

    return {
        "admin": admin,
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
    if request.flags.enabled(AdminFlagValue.DISABLE_ORGANIZATIONS):
        raise HTTPNotFound

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

    create_event = (
        organization.events.filter(Organization.Event.tag == "organization:create")
        .order_by(Organization.Event.time.desc())
        .first()
    )
    user = user_service.get_user(create_event.additional["created_by_user_id"])

    message = request.params.get("message", "")

    organization_service.approve_organization(organization.id)
    organization_service.record_event(
        organization.id,
        tag="organization:approve",
        additional={"approved_by_user_id": str(request.user.id)},
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
    if request.flags.enabled(AdminFlagValue.DISABLE_ORGANIZATIONS):
        raise HTTPNotFound

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

    create_event = (
        organization.events.filter(Organization.Event.tag == "organization:create")
        .order_by(Organization.Event.time.desc())
        .first()
    )
    user = user_service.get_user(create_event.additional["created_by_user_id"])

    message = request.params.get("message", "")

    organization_service.decline_organization(organization.id)
    organization_service.record_event(
        organization.id,
        tag="organization:decline",
        additional={"declined_by_user_id": str(request.user.id)},
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
