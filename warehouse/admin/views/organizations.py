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
from warehouse.authnz import Permissions
from warehouse.events.tags import EventTag
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import (
    Organization,
    OrganizationApplication,
    OrganizationType,
)
from warehouse.utils.paginate import paginate_url_factory


@view_config(
    route_name="admin.organization.list",
    renderer="admin/organizations/list.html",
    permission=Permissions.AdminOrganizationsRead,
    uses_session=True,
)
def organization_list(request):
    q = request.params.get("q", "")
    terms = shlex.split(q)

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    organizations_query = request.db.query(Organization).order_by(
        Organization.normalized_name
    )

    if q:
        filters = []
        for term in terms:
            # Examples:
            # - search individual words or "whole phrase" in any field
            # - name:psf
            # - org:python
            # - organization:python
            # - url:.org
            # - desc:word
            # - description:word
            # - description:"whole phrase"
            # - is:active
            # - is:inactive
            # - type:company
            # - type:community
            try:
                field, value = term.lower().split(":", 1)
            except ValueError:
                field, value = "", term
            if field == "name":
                # Add filter for `name` or `normalized_name` fields.
                filters.append(
                    [
                        Organization.name.ilike(f"%{value}%"),
                        Organization.normalized_name.ilike(f"%{value}%"),
                    ]
                )
            elif field == "org" or field == "organization":
                # Add filter for `display_name` field.
                filters.append(Organization.display_name.ilike(f"%{value}%"))
            elif field == "url" or field == "link_url":
                # Add filter for `link_url` field.
                filters.append(Organization.link_url.ilike(f"%{value}%"))
            elif field == "desc" or field == "description":
                # Add filter for `description` field.
                filters.append(Organization.description.ilike(f"%{value}%"))
            elif field == "is":
                # Add filter for `is_active` field.
                if "active".startswith(value):
                    filters.append(Organization.is_active == True)  # noqa: E712
                elif "inactive".startswith(value):
                    filters.append(Organization.is_active == False)  # noqa: E712
            elif field == "type":
                if "company".startswith(value):
                    filters.append(Organization.orgtype == OrganizationType.Company)
                elif "community".startswith(value):
                    filters.append(Organization.orgtype == OrganizationType.Community)
            else:
                # Add filter for any field.
                filters.append(
                    [
                        Organization.name.ilike(f"%{term}%"),
                        Organization.normalized_name.ilike(f"%{term}%"),
                        Organization.display_name.ilike(f"%{term}%"),
                        Organization.link_url.ilike(f"%{term}%"),
                        Organization.description.ilike(f"%{term}%"),
                    ]
                )
        # Use AND to add each filter. Use OR to combine subfilters.
        for filter_or_subfilters in filters:
            if isinstance(filter_or_subfilters, list):
                # Add list of subfilters combined with OR.
                filter_or_subfilters = filter_or_subfilters or [True]
                organizations_query = organizations_query.filter(
                    or_(False, *filter_or_subfilters)
                )
            else:
                # Add single filter.
                organizations_query = organizations_query.filter(filter_or_subfilters)

    organizations = SQLAlchemyORMPage(
        organizations_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {"organizations": organizations, "query": q, "terms": terms}


@view_config(
    route_name="admin.organization.detail",
    require_methods=False,
    renderer="admin/organizations/detail.html",
    permission=Permissions.AdminOrganizationsRead,
    has_translations=True,
    uses_session=True,
    require_csrf=True,
    require_reauth=True,
)
def organization_detail(request):
    organization_service = request.find_service(IOrganizationService, context=None)
    user_service = request.find_service(IUserService, context=None)

    organization_id = request.matchdict["organization_id"]
    organization = organization_service.get_organization(organization_id)
    if organization is None:
        raise HTTPNotFound

    create_event = (
        organization.events.filter(
            Organization.Event.tag == EventTag.Organization.OrganizationCreate
        )
        .order_by(Organization.Event.time.desc())
        .first()
    )
    user = (
        user_service.get_user(create_event.additional["created_by_user_id"])
        if create_event
        else None
    )

    if organization.is_approved is True:
        approve_event = (
            organization.events.filter(
                Organization.Event.tag == EventTag.Organization.OrganizationApprove
            )
            .order_by(Organization.Event.time.desc())
            .first()
        )
        approved_by_user_id = (
            approve_event.additional.get("approved_by_user_id")
            if approve_event
            else None
        )
        admin = (
            user_service.get_user(approved_by_user_id) if approved_by_user_id else None
        )
    elif organization.is_approved is False:
        decline_event = (
            organization.events.filter(
                Organization.Event.tag == EventTag.Organization.OrganizationDecline
            )
            .order_by(Organization.Event.time.desc())
            .first()
        )
        declined_by_user_id = (
            decline_event.additional.get("declined_by_user_id")
            if decline_event
            else None
        )
        admin = (
            user_service.get_user(declined_by_user_id) if declined_by_user_id else None
        )
    else:
        admin = None

    return {
        "admin": admin,
        "organization": organization,
        "user": user,
    }


@view_config(
    route_name="admin.organization_application.list",
    renderer="admin/organization_applications/list.html",
    permission=Permissions.AdminOrganizationsRead,
    uses_session=True,
)
def organization_applications_list(request):
    q = request.params.get("q", "")
    terms = shlex.split(q)

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    organization_applications_query = request.db.query(
        OrganizationApplication
    ).order_by(OrganizationApplication.normalized_name)

    if q:
        filters = []
        for term in terms:
            # Examples:
            # - search individual words or "whole phrase" in any field
            # - name:psf
            # - org:python
            # - organization:python
            # - url:.org
            # - desc:word
            # - description:word
            # - description:"whole phrase"
            # - is:approved
            # - is:declined
            # - is:submitted
            # - type:company
            # - type:community
            try:
                field, value = term.lower().split(":", 1)
            except ValueError:
                field, value = "", term
            if field == "name":
                # Add filter for `name` or `normalized_name` fields.
                filters.append(
                    [
                        OrganizationApplication.name.ilike(f"%{value}%"),
                        OrganizationApplication.normalized_name.ilike(f"%{value}%"),
                    ]
                )
            elif field == "org" or field == "organization":
                # Add filter for `display_name` field.
                filters.append(OrganizationApplication.display_name.ilike(f"%{value}%"))
            elif field == "url" or field == "link_url":
                # Add filter for `link_url` field.
                filters.append(OrganizationApplication.link_url.ilike(f"%{value}%"))
            elif field == "desc" or field == "description":
                # Add filter for `description` field.
                filters.append(OrganizationApplication.description.ilike(f"%{value}%"))
            elif field == "type":
                if "company".startswith(value):
                    filters.append(
                        OrganizationApplication.orgtype == OrganizationType.Company
                    )
                elif "community".startswith(value):
                    filters.append(
                        OrganizationApplication.orgtype == OrganizationType.Community
                    )
            elif field == "is":
                # Add filter for `is_approved` field.
                if "approved".startswith(value):
                    filters.append(OrganizationApplication.is_approved.is_(True))
                elif "declined".startswith(value):
                    filters.append(OrganizationApplication.is_approved.is_(False))
                elif "submitted".startswith(value):
                    filters.append(OrganizationApplication.is_approved.is_(None))
            else:
                # Add filter for any field.
                filters.append(
                    [
                        OrganizationApplication.name.ilike(f"%{term}%"),
                        OrganizationApplication.normalized_name.ilike(f"%{term}%"),
                        OrganizationApplication.display_name.ilike(f"%{term}%"),
                        OrganizationApplication.link_url.ilike(f"%{term}%"),
                        OrganizationApplication.description.ilike(f"%{term}%"),
                    ]
                )
        # Use AND to add each filter. Use OR to combine subfilters.
        for filter_or_subfilters in filters:
            if isinstance(filter_or_subfilters, list):
                # Add list of subfilters combined with OR.
                filter_or_subfilters = filter_or_subfilters or [True]
                organization_applications_query = (
                    organization_applications_query.filter(
                        or_(False, *filter_or_subfilters)
                    )
                )
            else:
                # Add single filter.
                organization_applications_query = (
                    organization_applications_query.filter(filter_or_subfilters)
                )

    organization_applications = SQLAlchemyORMPage(
        organization_applications_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {
        "organization_applications": organization_applications,
        "query": q,
        "terms": terms,
    }


@view_config(
    route_name="admin.organization_application.detail",
    require_methods=False,
    renderer="admin/organization_applications/detail.html",
    permission=Permissions.AdminOrganizationsRead,
    has_translations=True,
    uses_session=True,
    require_csrf=True,
    require_reauth=True,
)
def organization_application_detail(request):
    organization_service = request.find_service(IOrganizationService, context=None)
    user_service = request.find_service(IUserService, context=None)

    organization_application_id = request.matchdict["organization_application_id"]
    organization_application = organization_service.get_organization_application(
        organization_application_id
    )
    if organization_application is None:
        raise HTTPNotFound

    user = user_service.get_user(organization_application.submitted_by_id)

    return {
        "organization_application": organization_application,
        "user": user,
    }


@view_config(
    route_name="admin.organization_application.approve",
    require_methods=["POST"],
    renderer="admin/organization_applicationss/approve.html",
    permission=Permissions.AdminOrganizationsWrite,
    has_translations=True,
    uses_session=True,
    require_csrf=True,
    require_reauth=True,
)
def organization_application_approve(request):
    organization_service = request.find_service(IOrganizationService, context=None)

    organization_application_id = request.matchdict["organization_application_id"]
    organization_application = organization_service.get_organization_application(
        organization_application_id
    )
    if organization_application is None:
        raise HTTPNotFound
    elif organization_application.name != request.params.get("organization_name"):
        request.session.flash("Wrong confirmation input", queue="error")
        return HTTPSeeOther(
            request.route_path(
                "admin.organization_application.detail",
                organization_application_id=organization_application.id,
            )
        )

    organization = organization_service.approve_organization_application(
        organization_application.id, request
    )

    request.session.flash(
        f'Request for "{organization.name}" organization approved', queue="success"
    )

    return HTTPSeeOther(
        request.route_path("admin.organization.detail", organization_id=organization.id)
    )


@view_config(
    route_name="admin.organization_application.decline",
    require_methods=["POST"],
    renderer="admin/organization_applications/decline.html",
    permission=Permissions.AdminOrganizationsWrite,
    has_translations=True,
    uses_session=True,
    require_csrf=True,
    require_reauth=True,
)
def organization_application_decline(request):
    organization_service = request.find_service(IOrganizationService, context=None)

    organization_application_id = request.matchdict["organization_application_id"]
    organization_application = organization_service.get_organization_application(
        organization_application_id
    )
    if organization_application is None:
        raise HTTPNotFound
    elif organization_application.name != request.params.get("organization_name"):
        request.session.flash("Wrong confirmation input", queue="error")
        return HTTPSeeOther(
            request.route_path(
                "admin.organization_application.detail",
                organization_application_id=organization_application.id,
            )
        )

    organization_service.decline_organization_application(
        organization_application.id, request
    )

    request.session.flash(
        f'Request for "{organization_application.name}" organization declined',
        queue="success",
    )

    return HTTPSeeOther(
        request.route_path(
            "admin.organization_application.detail",
            organization_application_id=organization_application.id,
        )
    )
