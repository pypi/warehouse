# SPDX-License-Identifier: Apache-2.0

import datetime
import shlex

import wtforms

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy import desc, func, or_
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import joinedload

from warehouse.accounts.interfaces import IUserService
from warehouse.accounts.models import User
from warehouse.admin.forms import SetTotalSizeLimitForm, SetUploadLimitForm
from warehouse.authnz import Permissions
from warehouse.constants import (
    MAX_FILESIZE,
    MAX_PROJECT_SIZE,
    ONE_GIB,
    ONE_MIB,
    UPLOAD_LIMIT_CAP,
)
from warehouse.manage.forms import OrganizationNameMixin, SaveOrganizationForm
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import (
    Organization,
    OrganizationApplication,
    OrganizationApplicationStatus,
    OrganizationManualActivation,
    OrganizationRole,
    OrganizationRoleType,
    OrganizationType,
)
from warehouse.subscriptions.interfaces import IBillingService
from warehouse.utils.paginate import paginate_url_factory


class OrganizationRoleForm(wtforms.Form):
    role_name = wtforms.SelectField(
        choices=[(role.value, role.value) for role in OrganizationRoleType],
        coerce=OrganizationRoleType,
        validators=[
            wtforms.validators.InputRequired(message="Select a role"),
        ],
    )


class AddOrganizationRoleForm(wtforms.Form):
    username = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message="Specify username"),
        ]
    )
    role_name = wtforms.SelectField(
        choices=[(role.value, role.value) for role in OrganizationRoleType],
        coerce=OrganizationRoleType,
        validators=[
            wtforms.validators.InputRequired(message="Select a role"),
        ],
    )


class OrganizationForm(wtforms.Form):
    display_name = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(
                message="Specify organization display name"
            ),
            wtforms.validators.Length(
                max=100,
                message="Organization display name must be 100 characters or less",
            ),
        ]
    )

    link_url = wtforms.URLField(
        validators=[
            wtforms.validators.InputRequired(message="Specify organization URL"),
            wtforms.validators.Length(
                max=400, message="Organization URL must be 400 characters or less"
            ),
            wtforms.validators.Regexp(
                r"^https?://",
                message="Organization URL must start with http:// or https://",
            ),
        ]
    )

    description = wtforms.TextAreaField(
        validators=[
            wtforms.validators.InputRequired(
                message="Specify organization description"
            ),
            wtforms.validators.Length(
                max=400,
                message="Organization description must be 400 characters or less",
            ),
        ]
    )

    orgtype = wtforms.SelectField(
        choices=[(orgtype.value, orgtype.value) for orgtype in OrganizationType],
        coerce=OrganizationType,
        validators=[
            wtforms.validators.InputRequired(message="Select organization type"),
        ],
    )


class ManualActivationForm(wtforms.Form):
    seat_limit = wtforms.IntegerField(
        validators=[
            wtforms.validators.InputRequired(message="Specify seat limit"),
            wtforms.validators.NumberRange(
                min=1, message="Seat limit must be at least 1"
            ),
        ]
    )

    expires = wtforms.DateField(
        validators=[
            wtforms.validators.InputRequired(message="Specify expiration date"),
        ]
    )

    def validate_expires(self, field):
        if field.data and field.data <= datetime.date.today():
            raise wtforms.ValidationError("Expiration date must be in the future")


def _turbo_mode(request):
    next_organization_application = (
        request.db.query(OrganizationApplication)
        .filter(OrganizationApplication.status == "submitted")
        .order_by(OrganizationApplication.submitted)
        .first()
    )
    if next_organization_application:
        return HTTPSeeOther(
            request.route_path(
                "admin.organization_application.detail",
                organization_application_id=next_organization_application.id,
            )
        )
    else:
        request.session.flash(
            "No more Organization Applications to review!", queue="success"
        )
        return HTTPSeeOther(request.route_path("admin.dashboard"))


@view_config(
    route_name="admin.organization.list",
    renderer="warehouse.admin:templates/admin/organizations/list.html",
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

    organizations_query = (
        request.db.query(Organization)
        .options(joinedload(Organization.subscriptions))
        .order_by(Organization.normalized_name)
    )

    if q:
        filters: list = []
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
    renderer="warehouse.admin:templates/admin/organizations/detail.html",
    permission=Permissions.AdminOrganizationsRead,
    request_method="GET",
    has_translations=True,
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
@view_config(
    route_name="admin.organization.detail",
    renderer="warehouse.admin:templates/admin/organizations/detail.html",
    permission=Permissions.AdminOrganizationsWrite,
    request_method="POST",
    has_translations=True,
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def organization_detail(request):
    organization_service = request.find_service(IOrganizationService, context=None)
    billing_service = request.find_service(IBillingService, context=None)

    organization_id = request.matchdict["organization_id"]
    organization = organization_service.get_organization(organization_id)
    if organization is None:
        raise HTTPNotFound

    form = OrganizationForm(
        request.POST if request.method == "POST" else None,
        organization,
    )

    if request.method == "POST" and form.validate():
        form.populate_obj(organization)

        # Update Stripe customer if organization has one
        if organization.customer is not None:
            billing_service.update_customer(
                organization.customer.customer_id,
                organization.customer_name(request.registry.settings["site.name"]),
                organization.description,
            )

        request.session.flash(
            f"Organization {organization.name!r} updated successfully",
            queue="success",
        )
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    # Sort roles by username
    roles = sorted(organization.roles, key=lambda r: r.user.username)

    # Create role forms for each existing role
    role_forms = {role.id: OrganizationRoleForm(obj=role) for role in roles}

    # Create form for adding new roles
    add_role_form = AddOrganizationRoleForm()

    # Create form for manual activation
    manual_activation_form = ManualActivationForm()

    return {
        "organization": organization,
        "form": form,
        "roles": roles,
        "role_forms": role_forms,
        "add_role_form": add_role_form,
        "manual_activation_form": manual_activation_form,
        "ONE_MIB": ONE_MIB,
        "MAX_FILESIZE": MAX_FILESIZE,
        "ONE_GIB": ONE_GIB,
        "MAX_PROJECT_SIZE": MAX_PROJECT_SIZE,
        "UPLOAD_LIMIT_CAP": UPLOAD_LIMIT_CAP,
    }


@view_config(
    route_name="admin.organization.rename",
    require_methods=["POST"],
    permission=Permissions.AdminOrganizationsNameWrite,
    has_translations=True,
    uses_session=True,
    require_csrf=True,
)
def organization_rename(request):
    organization_service = request.find_service(IOrganizationService, context=None)

    organization_id = request.matchdict["organization_id"]
    organization = organization_service.get_organization(organization_id)
    if organization is None:
        raise HTTPNotFound

    old_organization_name = organization.name
    new_organization_name = request.params.get("new_organization_name").strip()

    try:
        organization_service.rename_organization(organization_id, new_organization_name)
    except ValueError as exc:
        request.session.flash(exc.args[0], queue="error")
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    request.session.flash(
        f'"{old_organization_name}" organization renamed "{new_organization_name}"',
        queue="success",
    )

    return HTTPSeeOther(
        request.route_path("admin.organization.detail", organization_id=organization.id)
    )


@view_config(
    route_name="admin.organization_application.list",
    renderer="warehouse.admin:templates/admin/organization_applications/list.html",
    permission=Permissions.AdminOrganizationsRead,
    uses_session=True,
)
def organization_applications_list(request):
    q = request.params.get("q", "")
    terms = shlex.split(q)

    organization_applications_query = request.db.query(
        OrganizationApplication
    ).order_by(OrganizationApplication.submitted)

    if q:
        filters: list = []
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
            # - is:submitted
            # - is:declined
            # - is:deferred
            # - is:moreinformationneeded
            # - is:approved
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
                if value in OrganizationApplicationStatus:
                    filters.append(OrganizationApplication.status == value)
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

    organization_applications_query = organization_applications_query.options(
        joinedload(OrganizationApplication.observations)
    )

    return {
        "organization_applications": organization_applications_query.all(),
        "query": q,
        "terms": terms,
    }


class OrganizationApplicationForm(OrganizationNameMixin, SaveOrganizationForm):
    def __init__(self, *args, organization_service, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization_service = organization_service
        self.user = user


@view_config(
    route_name="admin.organization_application.detail",
    require_methods=False,
    renderer="warehouse.admin:templates/admin/organization_applications/detail.html",
    permission=Permissions.AdminOrganizationsRead,
    has_translations=True,
    uses_session=True,
    require_csrf=True,
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

    form = OrganizationApplicationForm(
        request.POST if request.method == "POST" else None,
        organization_application,
        organization_service=organization_service,
        user=request.user,
    )

    if request.method == "POST" and form.validate():
        form.populate_obj(organization_application)
        request.session.flash(
            f"Application for {organization_application.name!r} updated",
            queue="success",
        )
        return HTTPSeeOther(location=request.current_route_path())

    parts = organization_application.normalized_name.split("-")
    conflicting_applications = (
        request.db.query(OrganizationApplication)
        .filter(
            or_(
                *(
                    [
                        OrganizationApplication.normalized_name == parts[0],
                        OrganizationApplication.normalized_name.startswith(
                            parts[0] + "-"
                        ),
                    ]
                    + [
                        OrganizationApplication.normalized_name.startswith(
                            "-".join(parts[: i + 1])
                        )
                        for i in range(1, len(parts))
                    ]
                )
            )
        )
        .filter(OrganizationApplication.id != organization_application.id)
        .order_by(
            desc(
                func.similarity(
                    OrganizationApplication.normalized_name,
                    organization_application.normalized_name,
                )
            )
        )
        .all()
    )

    user = user_service.get_user(organization_application.submitted_by_id)

    return {
        "organization_application": organization_application,
        "form": form,
        "conflicting_applications": conflicting_applications,
        "user": user,
    }


@view_config(
    route_name="admin.organization_application.approve",
    require_methods=["POST"],
    permission=Permissions.AdminOrganizationsWrite,
    has_translations=True,
    uses_session=True,
    require_csrf=True,
)
def organization_application_approve(request):
    organization_service = request.find_service(IOrganizationService, context=None)

    organization_application_id = request.matchdict["organization_application_id"]
    organization_application = organization_service.get_organization_application(
        organization_application_id
    )
    if organization_application is None:
        raise HTTPNotFound

    organization = organization_service.approve_organization_application(
        organization_application.id, request
    )

    request.session.flash(
        f'Request for "{organization.name}" organization approved', queue="success"
    )

    if request.params.get("organization_applications_turbo_mode") == "true":
        return _turbo_mode(request)

    return HTTPSeeOther(
        request.route_path("admin.organization.detail", organization_id=organization.id)
    )


@view_config(
    route_name="admin.organization_application.defer",
    require_methods=["POST"],
    permission=Permissions.AdminOrganizationsWrite,
    has_translations=True,
    uses_session=True,
    require_csrf=True,
)
def organization_application_defer(request):
    organization_service = request.find_service(IOrganizationService, context=None)

    organization_application_id = request.matchdict["organization_application_id"]
    organization_application = organization_service.get_organization_application(
        organization_application_id
    )
    if organization_application is None:
        raise HTTPNotFound

    organization_service.defer_organization_application(
        organization_application.id, request
    )

    request.session.flash(
        f'Request for "{organization_application.name}" organization deferred',
        queue="success",
    )

    if request.params.get("organization_applications_turbo_mode") == "true":
        return _turbo_mode(request)

    return HTTPSeeOther(
        request.route_path(
            "admin.organization_application.detail",
            organization_application_id=organization_application.id,
        )
    )


@view_config(
    route_name="admin.organization_application.requestmoreinfo",
    require_methods=["POST"],
    permission=Permissions.AdminOrganizationsWrite,
    has_translations=True,
    uses_session=True,
    require_csrf=True,
)
def organization_application_request_more_information(request):
    organization_service = request.find_service(IOrganizationService, context=None)

    organization_application_id = request.matchdict["organization_application_id"]
    organization_application = organization_service.get_organization_application(
        organization_application_id
    )
    if organization_application is None:
        raise HTTPNotFound

    try:
        organization_service.request_more_information(
            organization_application.id, request
        )
        request.session.flash(
            (
                f'Request for more info from "{organization_application.name}" '
                "organization sent"
            ),
            queue="success",
        )

        if request.params.get("organization_applications_turbo_mode") == "true":
            return _turbo_mode(request)
    except ValueError:
        request.session.flash("No message provided", queue="error")

    return HTTPSeeOther(
        request.route_path(
            "admin.organization_application.detail",
            organization_application_id=organization_application.id,
        )
    )


@view_config(
    route_name="admin.organization_application.decline",
    require_methods=["POST"],
    permission=Permissions.AdminOrganizationsWrite,
    has_translations=True,
    uses_session=True,
    require_csrf=True,
)
def organization_application_decline(request):
    organization_service = request.find_service(IOrganizationService, context=None)

    organization_application_id = request.matchdict["organization_application_id"]
    organization_application = organization_service.get_organization_application(
        organization_application_id
    )
    if organization_application is None:
        raise HTTPNotFound

    organization_service.decline_organization_application(
        organization_application.id, request
    )

    request.session.flash(
        f'Request for "{organization_application.name}" organization declined',
        queue="success",
    )

    if request.params.get("organization_applications_turbo_mode") == "true":
        return _turbo_mode(request)

    return HTTPSeeOther(
        request.route_path(
            "admin.organization_application.detail",
            organization_application_id=organization_application.id,
        )
    )


@view_config(
    route_name="admin.organization.add_role",
    permission=Permissions.AdminRoleAdd,
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def add_organization_role(request):
    organization_service = request.find_service(IOrganizationService, context=None)

    organization_id = request.matchdict["organization_id"]
    organization = organization_service.get_organization(organization_id)
    if organization is None:
        raise HTTPNotFound

    username = request.POST.get("username")
    if not username:
        request.session.flash("Provide a username", queue="error")
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    try:
        user = request.db.query(User).filter(User.username == username).one()
    except NoResultFound:
        request.session.flash(f"Unknown username '{username}'", queue="error")
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    role_name = request.POST.get("role_name")
    if not role_name:
        request.session.flash("Provide a role", queue="error")
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    # Check if user already has a role in this organization
    already_there = (
        request.db.query(OrganizationRole)
        .filter(
            OrganizationRole.user == user, OrganizationRole.organization == organization
        )
        .count()
    )
    if already_there > 0:
        request.session.flash(
            f"User '{user.username}' already has a role in this organization",
            queue="error",
        )
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    # Create the role
    organization_role = OrganizationRole(
        role_name=OrganizationRoleType(role_name),
        user=user,
        organization=organization,
    )
    request.db.add(organization_role)

    # Record the event
    organization.record_event(
        request=request,
        tag="admin:organization:role:add",
        additional={
            "action": f"add {role_name} {user.username}",
            "user_id": str(user.id),
            "role_name": role_name,
        },
    )

    request.session.flash(
        f"Added '{user.username}' as '{role_name}' to '{organization.name}'",
        queue="success",
    )

    return HTTPSeeOther(
        request.route_path("admin.organization.detail", organization_id=organization.id)
    )


@view_config(
    route_name="admin.organization.update_role",
    permission=Permissions.AdminRoleUpdate,
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def update_organization_role(request):
    organization_service = request.find_service(IOrganizationService, context=None)

    organization_id = request.matchdict["organization_id"]
    organization = organization_service.get_organization(organization_id)
    if organization is None:
        raise HTTPNotFound

    role_id = request.matchdict.get("role_id")
    role = request.db.get(OrganizationRole, role_id)
    if not role:
        request.session.flash("This role no longer exists", queue="error")
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    new_role_name = request.POST.get("role_name")
    if not new_role_name:
        request.session.flash("Provide a role", queue="error")
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    # Don't update if it's the same role
    if role.role_name.value == new_role_name:
        request.session.flash("Role is already set to this value", queue="error")
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    old_role_name = role.role_name.value

    # Update the role
    role.role_name = OrganizationRoleType(new_role_name)
    request.db.add(role)
    request.db.flush()  # Ensure the role is updated before recording event

    # Record the event
    organization.record_event(
        request=request,
        tag="admin:organization:role:change",
        additional={
            "action": (
                f"change {role.user.username} from {old_role_name} to {new_role_name}"
            ),
            "user_id": str(role.user.id),
            "old_role_name": old_role_name,
            "new_role_name": new_role_name,
        },
    )

    request.session.flash(
        f"Changed '{role.user.username}' from '{old_role_name}' to "
        f"'{new_role_name}' in '{organization.name}'",
        queue="success",
    )

    return HTTPSeeOther(
        request.route_path("admin.organization.detail", organization_id=organization.id)
    )


@view_config(
    route_name="admin.organization.delete_role",
    permission=Permissions.AdminRoleDelete,
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def delete_organization_role(request):
    organization_service = request.find_service(IOrganizationService, context=None)

    organization_id = request.matchdict["organization_id"]
    organization = organization_service.get_organization(organization_id)
    if organization is None:
        raise HTTPNotFound

    role_id = request.matchdict.get("role_id")
    role = request.db.get(OrganizationRole, role_id)
    if not role:
        request.session.flash("This role no longer exists", queue="error")
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    confirm = request.POST.get("username")
    if not confirm or confirm != role.user.username:
        request.session.flash("Confirm the request", queue="error")
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    # Record the event before deleting
    organization.record_event(
        request=request,
        tag="admin:organization:role:remove",
        additional={
            "action": f"remove {role.role_name.value} {role.user.username}",
            "user_id": str(role.user.id),
            "role_name": role.role_name.value,
        },
    )

    request.session.flash(
        f"Removed '{role.user.username}' as '{role.role_name.value}' "
        f"from '{organization.name}'",
        queue="success",
    )

    request.db.delete(role)

    return HTTPSeeOther(
        request.route_path("admin.organization.detail", organization_id=organization.id)
    )


@view_config(
    route_name="admin.organization.add_manual_activation",
    permission=Permissions.AdminOrganizationsWrite,
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def add_manual_activation(request):
    organization_service = request.find_service(IOrganizationService, context=None)

    organization_id = request.matchdict["organization_id"]
    organization = organization_service.get_organization(organization_id)
    if organization is None:
        raise HTTPNotFound

    # Check if organization already has manual activation
    existing_activation = (
        request.db.query(OrganizationManualActivation)
        .filter(OrganizationManualActivation.organization_id == organization.id)
        .first()
    )

    if existing_activation:
        request.session.flash(
            f"Organization '{organization.name}' already has manual activation",
            queue="error",
        )
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    form = ManualActivationForm(request.POST)
    if not form.validate():
        for field, errors in form.errors.items():
            for error in errors:
                request.session.flash(f"{field}: {error}", queue="error")
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    # Create manual activation
    manual_activation = OrganizationManualActivation(
        organization_id=organization.id,
        seat_limit=form.seat_limit.data,
        expires=form.expires.data,
        created_by_id=request.user.id,
    )
    request.db.add(manual_activation)

    # Record the event
    organization.record_event(
        request=request,
        tag="admin:organization:manual_activation:add",
        additional={
            "seat_limit": form.seat_limit.data,
            "expires": form.expires.data.isoformat(),
        },
    )

    request.session.flash(
        f"Manual activation added for '{organization.name}' "
        f"(seat limit: {form.seat_limit.data}, expires: {form.expires.data})",
        queue="success",
    )

    return HTTPSeeOther(
        request.route_path("admin.organization.detail", organization_id=organization.id)
    )


@view_config(
    route_name="admin.organization.set_upload_limit",
    permission=Permissions.AdminOrganizationsSetLimit,
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def set_upload_limit(request):
    organization_id = request.matchdict["organization_id"]
    organization = request.db.query(Organization).get(organization_id)
    if organization is None:
        raise HTTPNotFound

    form = SetUploadLimitForm(request.POST)

    if not form.validate():
        for field, errors in form.errors.items():
            for error in errors:
                request.session.flash(f"{field}: {error}", queue="error")
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    # Form validation has already converted to bytes or None
    organization.upload_limit = form.upload_limit.data

    if organization.upload_limit:
        limit_msg = f"{organization.upload_limit / ONE_MIB}MiB"
    else:
        limit_msg = "(default)"
    request.session.flash(
        f"Upload limit set to {limit_msg}",
        queue="success",
    )

    return HTTPSeeOther(
        request.route_path(
            "admin.organization.detail",
            organization_id=organization.id,
        )
    )


@view_config(
    route_name="admin.organization.update_manual_activation",
    permission=Permissions.AdminOrganizationsWrite,
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def update_manual_activation(request):
    organization_service = request.find_service(IOrganizationService, context=None)

    organization_id = request.matchdict["organization_id"]
    organization = organization_service.get_organization(organization_id)
    if organization is None:
        raise HTTPNotFound

    manual_activation = (
        request.db.query(OrganizationManualActivation)
        .filter(OrganizationManualActivation.organization_id == organization.id)
        .first()
    )

    if not manual_activation:
        request.session.flash(
            f"Organization '{organization.name}' has no manual activation to update",
            queue="error",
        )
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    form = ManualActivationForm(request.POST)
    if not form.validate():
        for field, errors in form.errors.items():
            for error in errors:
                request.session.flash(f"{field}: {error}", queue="error")
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    old_seat_limit = manual_activation.seat_limit
    old_expires = manual_activation.expires

    # Update manual activation
    manual_activation.seat_limit = form.seat_limit.data
    manual_activation.expires = form.expires.data
    manual_activation.created_by_id = request.user.id
    request.db.add(manual_activation)

    # Record the event
    organization.record_event(
        request=request,
        tag="admin:organization:manual_activation:update",
        additional={
            "old_seat_limit": old_seat_limit,
            "new_seat_limit": form.seat_limit.data,
            "old_expires": old_expires.isoformat(),
            "new_expires": form.expires.data.isoformat(),
        },
    )

    request.session.flash(
        f"Manual activation updated for '{organization.name}' "
        f"(seat limit: {form.seat_limit.data}, expires: {form.expires.data})",
        queue="success",
    )

    return HTTPSeeOther(
        request.route_path("admin.organization.detail", organization_id=organization.id)
    )


@view_config(
    route_name="admin.organization.delete_manual_activation",
    permission=Permissions.AdminOrganizationsWrite,
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def delete_manual_activation(request):
    organization_service = request.find_service(IOrganizationService, context=None)

    organization_id = request.matchdict["organization_id"]
    organization = organization_service.get_organization(organization_id)
    if organization is None:
        raise HTTPNotFound

    manual_activation = (
        request.db.query(OrganizationManualActivation)
        .filter(OrganizationManualActivation.organization_id == organization.id)
        .first()
    )

    if not manual_activation:
        request.session.flash(
            f"Organization '{organization.name}' has no manual activation to delete",
            queue="error",
        )
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    confirm = request.POST.get("confirm")
    if not confirm or confirm != organization.name:
        request.session.flash("Confirm the request", queue="error")
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    # Record the event before deleting
    organization.record_event(
        request=request,
        tag="admin:organization:manual_activation:delete",
        additional={
            "seat_limit": manual_activation.seat_limit,
            "expires": manual_activation.expires.isoformat(),
        },
    )

    request.session.flash(
        f"Manual activation removed from '{organization.name}'",
        queue="success",
    )

    request.db.delete(manual_activation)

    return HTTPSeeOther(
        request.route_path("admin.organization.detail", organization_id=organization.id)
    )


@view_config(
    route_name="admin.organization.set_total_size_limit",
    permission=Permissions.AdminOrganizationsSetLimit,
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def set_total_size_limit(request):
    organization_id = request.matchdict["organization_id"]
    organization = request.db.query(Organization).get(organization_id)
    if organization is None:
        raise HTTPNotFound

    form = SetTotalSizeLimitForm(request.POST)

    if not form.validate():
        for field, errors in form.errors.items():
            for error in errors:
                request.session.flash(f"{field}: {error}", queue="error")
        return HTTPSeeOther(
            request.route_path(
                "admin.organization.detail", organization_id=organization.id
            )
        )

    # Form validation has already converted to bytes or None
    organization.total_size_limit = form.total_size_limit.data

    if organization.total_size_limit:
        limit_msg = f"{organization.total_size_limit / ONE_GIB}GiB"
    else:
        limit_msg = "(default)"
    request.session.flash(
        f"Total size limit set to {limit_msg}",
        queue="success",
    )

    return HTTPSeeOther(
        request.route_path(
            "admin.organization.detail",
            organization_id=organization.id,
        )
    )
