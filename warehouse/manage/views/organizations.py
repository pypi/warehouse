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
from urllib.parse import urljoin

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPException,
    HTTPNotFound,
    HTTPSeeOther,
)
from pyramid.view import view_config, view_defaults
from sqlalchemy import orm
from webob.multidict import MultiDict

from warehouse.accounts.interfaces import ITokenService, IUserService, TokenExpired
from warehouse.accounts.models import User
from warehouse.email import (
    send_admin_organization_deleted_email,
    send_admin_organization_renamed_email,
    send_canceled_as_invited_organization_member_email,
    send_new_organization_requested_email,
    send_organization_deleted_email,
    send_organization_member_invite_canceled_email,
    send_organization_member_invited_email,
    send_organization_member_removed_email,
    send_organization_member_role_changed_email,
    send_organization_project_added_email,
    send_organization_project_removed_email,
    send_organization_renamed_email,
    send_organization_role_verification_email,
    send_organization_updated_email,
    send_removed_as_organization_member_email,
    send_role_changed_as_organization_member_email,
    send_team_created_email,
)
from warehouse.events.tags import EventTag
from warehouse.manage.forms import (
    AddOrganizationProjectForm,
    ChangeOrganizationRoleForm,
    CreateOrganizationApplicationForm,
    CreateOrganizationRoleForm,
    CreateTeamForm,
    SaveOrganizationForm,
    SaveOrganizationNameForm,
    TransferOrganizationProjectForm,
)
from warehouse.manage.views.view_helpers import (
    project_owners,
    user_organizations,
    user_projects,
)
from warehouse.organizations import IOrganizationService
from warehouse.organizations.models import (
    Organization,
    OrganizationInvitationStatus,
    OrganizationRole,
    OrganizationRoleType,
    OrganizationType,
)
from warehouse.packaging import IProjectService, Project, Role
from warehouse.packaging.models import JournalEntry, ProjectFactory
from warehouse.subscriptions import IBillingService, ISubscriptionService
from warehouse.subscriptions.services import MockStripeBillingService
from warehouse.utils.organization import confirm_organization
from warehouse.utils.paginate import paginate_url_factory
from warehouse.utils.project import confirm_project, validate_project_name


def organization_owners(request, organization):
    """Return all users who are owners of the organization."""
    owner_roles = (
        request.db.query(User.id)
        .join(OrganizationRole.user)
        .filter(
            OrganizationRole.role_name == OrganizationRoleType.Owner,
            OrganizationRole.organization == organization,
        )
        .subquery()
    )
    return request.db.query(User).join(owner_roles, User.id == owner_roles.c.id).all()


def organization_managers(request, organization):
    """Return all users who are managers of the organization."""
    manager_roles = (
        request.db.query(User.id)
        .join(OrganizationRole.user)
        .filter(
            OrganizationRole.role_name == OrganizationRoleType.Manager,
            OrganizationRole.organization == organization,
        )
        .subquery()
    )
    return (
        request.db.query(User).join(manager_roles, User.id == manager_roles.c.id).all()
    )


def organization_members(request, organization):
    """Return all users who are members of the organization."""
    member_roles = (
        request.db.query(User.id)
        .join(OrganizationRole.user)
        .filter(
            OrganizationRole.role_name == OrganizationRoleType.Member,
            OrganizationRole.organization == organization,
        )
        .subquery()
    )
    return request.db.query(User).join(member_roles, User.id == member_roles.c.id).all()


@view_defaults(
    route_name="manage.organizations",
    renderer="manage/organizations.html",
    uses_session=True,
    require_active_organization=False,  # Allow list/create orgs without active org.
    require_csrf=True,
    require_methods=False,
    permission="manage:user",
    has_translations=True,
)
class ManageOrganizationsViews:
    def __init__(self, request):
        self.request = request
        self.user_service = request.find_service(IUserService, context=None)
        self.organization_service = request.find_service(
            IOrganizationService, context=None
        )

    @property
    def default_response(self):
        all_user_organizations = user_organizations(self.request)

        # Get list of applications for Organizations
        organization_applications = self.request.user.organization_applications

        # Get list of invites as (organization, token) tuples.
        organization_invites = (
            self.organization_service.get_organization_invites_by_user(
                self.request.user.id
            )
        )
        organization_invites = [
            (organization_invite.organization, organization_invite.token)
            for organization_invite in organization_invites
        ]

        # Get list of organizations that are approved (True) or pending (None).
        organizations = self.organization_service.get_organizations_by_user(
            self.request.user.id
        )
        organizations = [
            organization
            for organization in organizations
            if organization.is_approved is not False
        ]

        return {
            "organization_invites": organization_invites,
            "organization_applications": organization_applications,
            "organizations": organizations,
            "organizations_managed": list(
                organization.name
                for organization in all_user_organizations["organizations_managed"]
            ),
            "organizations_owned": list(
                organization.name
                for organization in all_user_organizations["organizations_owned"]
            ),
            "organizations_billing": list(
                organization.name
                for organization in all_user_organizations["organizations_billing"]
            ),
            "create_organization_application_form": CreateOrganizationApplicationForm(
                organization_service=self.organization_service,
                user=self.request.user,
            )
            if len(
                [
                    app
                    for app in self.request.user.organization_applications
                    if app.is_approved is None
                ]
            )
            < self.request.registry.settings[
                "warehouse.organizations.max_undecided_organization_applications"
            ]
            else None,
        }

    @view_config(request_method="GET")
    def manage_organizations(self):
        # Organizations must be enabled.
        if not self.request.organization_access:
            raise HTTPNotFound()

        return self.default_response

    @view_config(
        request_method="POST",
        request_param=CreateOrganizationApplicationForm.__params__,
    )
    def create_organization_application(self):
        # Organizations must be enabled.
        if not self.request.organization_access:
            raise HTTPNotFound()

        form = CreateOrganizationApplicationForm(
            self.request.POST,
            organization_service=self.organization_service,
            user=self.request.user,
            max_apps=self.request.registry.settings[
                "warehouse.organizations.max_undecided_organization_applications"
            ],
        )

        if form.validate():
            data = form.data
            organization = self.organization_service.add_organization_application(
                **data, submitted_by=self.request.user
            )

            send_new_organization_requested_email(
                self.request, self.request.user, organization_name=organization.name
            )
            self.request.session.flash(
                "Request for new organization submitted", queue="success"
            )
        else:
            return {"create_organization_application_form": form}

        return HTTPSeeOther(self.request.path)


@view_defaults(
    route_name="manage.organization.settings",
    context=Organization,
    renderer="manage/organization/settings.html",
    uses_session=True,
    require_active_organization=True,
    require_csrf=True,
    require_methods=False,
    permission="manage:organization",
    has_translations=True,
    require_reauth=True,
)
class ManageOrganizationSettingsViews:
    def __init__(self, organization, request):
        self.organization = organization
        self.request = request
        self.user_service = request.find_service(IUserService, context=None)
        self.organization_service = request.find_service(
            IOrganizationService, context=None
        )
        self.billing_service = request.find_service(IBillingService, context=None)

    @property
    def active_projects(self):
        return self.organization.projects

    @property
    def default_response(self):
        return {
            "organization": self.organization,
            "save_organization_form": SaveOrganizationForm(
                MultiDict(
                    {
                        "name": self.organization.name,
                        "display_name": self.organization.display_name,
                        "link_url": self.organization.link_url,
                        "description": self.organization.description,
                        "orgtype": self.organization.orgtype,
                    }
                )
            ),
            "save_organization_name_form": SaveOrganizationNameForm(
                organization_service=self.organization_service,
                user=self.request.user,
            ),
            "active_projects": self.active_projects,
        }

    @view_config(request_method="GET", permission="view:organization")
    def manage_organization(self):
        return self.default_response

    @view_config(request_method="POST", request_param=SaveOrganizationForm.__params__)
    def save_organization(self):
        form = SaveOrganizationForm(self.request.POST, user=self.request.user)

        if form.validate():
            previous_organization_display_name = self.organization.display_name
            previous_organization_link_url = self.organization.link_url
            previous_organization_description = self.organization.description
            previous_organization_orgtype = self.organization.orgtype

            data = form.data
            if previous_organization_orgtype == OrganizationType.Company:
                # Disable changing Company account to Community account.
                data["orgtype"] = previous_organization_orgtype
            self.organization_service.update_organization(self.organization.id, **data)

            owner_users = set(organization_owners(self.request, self.organization))
            send_organization_updated_email(
                self.request,
                owner_users,
                organization_name=self.organization.name,
                organization_display_name=self.organization.display_name,
                organization_link_url=self.organization.link_url,
                organization_description=self.organization.description,
                organization_orgtype=self.organization.orgtype,
                previous_organization_display_name=previous_organization_display_name,
                previous_organization_link_url=previous_organization_link_url,
                previous_organization_description=previous_organization_description,
                previous_organization_orgtype=previous_organization_orgtype,
            )
            if self.organization.customer is not None:
                self.billing_service.update_customer(
                    self.organization.customer.customer_id,
                    self.organization.customer_name(
                        self.request.registry.settings["site.name"]
                    ),
                    self.organization.description,
                )

            self.request.session.flash("Organization details updated", queue="success")

            return HTTPSeeOther(self.request.path)

        return {**self.default_response, "save_organization_form": form}

    @view_config(
        request_method="POST",
        request_param=["confirm_current_organization_name"]
        + SaveOrganizationNameForm.__params__,
    )
    def save_organization_name(self):
        confirm_organization(
            self.organization,
            self.request,
            fail_route="manage.organization.settings",
            field_name="confirm_current_organization_name",
            error_message="Could not rename organization",
        )

        form = SaveOrganizationNameForm(
            self.request.POST,
            organization_service=self.organization_service,
            organization_id=self.organization.id,
            user=self.request.user,
        )

        if form.validate():
            previous_organization_name = self.organization.name
            self.organization_service.rename_organization(
                self.organization.id,
                form.name.data,
            )
            self.organization.record_event(
                tag=EventTag.Organization.CatalogEntryAdd,
                request=self.request,
                additional={"submitted_by_user_id": str(self.request.user.id)},
            )
            self.organization.record_event(
                tag=EventTag.Organization.OrganizationRename,
                request=self.request,
                additional={
                    "previous_organization_name": previous_organization_name,
                    "renamed_by_user_id": str(self.request.user.id),
                },
            )
            owner_users = set(organization_owners(self.request, self.organization))
            send_admin_organization_renamed_email(
                self.request,
                self.user_service.get_admin_user(),
                organization_name=self.organization.name,
                previous_organization_name=previous_organization_name,
            )
            send_organization_renamed_email(
                self.request,
                owner_users,
                organization_name=self.organization.name,
                previous_organization_name=previous_organization_name,
            )
            self.request.session.flash(
                "Organization account name updated", queue="success"
            )
            return HTTPSeeOther(
                self.request.route_path(
                    "manage.organization.settings",
                    organization_name=self.organization.normalized_name,
                )
                + "#modal-close"
            )

        return {**self.default_response, "save_organization_name_form": form}

    @view_config(request_method="POST", request_param=["confirm_organization_name"])
    def delete_organization(self):
        confirm_organization(
            self.organization, self.request, fail_route="manage.organization.settings"
        )

        if self.active_projects:
            self.request.session.flash(
                "Cannot delete organization with active project ownerships",
                queue="error",
            )
            return self.default_response

        # Record event before deleting organization.
        self.organization.record_event(
            tag=EventTag.Organization.OrganizationDelete,
            request=self.request,
            additional={
                "deleted_by_user_id": str(self.request.user.id),
            },
        )

        # Get owners before deleting organization.
        owner_users = set(organization_owners(self.request, self.organization))

        # Cancel any subscriptions tied to this organization.
        if self.organization.subscriptions:
            for subscription in self.organization.subscriptions:
                self.billing_service.cancel_subscription(subscription.subscription_id)

        self.organization_service.delete_organization(self.organization.id)

        send_admin_organization_deleted_email(
            self.request,
            self.user_service.get_admin_user(),
            organization_name=self.organization.name,
        )
        send_organization_deleted_email(
            self.request,
            owner_users,
            organization_name=self.organization.name,
        )

        return HTTPSeeOther(self.request.route_path("manage.organizations"))


@view_defaults(
    context=Organization,
    uses_session=True,
    require_active_organization=False,  # Allow reactivate billing for inactive org.
    require_csrf=True,
    require_methods=False,
    permission="manage:billing",
    has_translations=True,
    require_reauth=True,
)
class ManageOrganizationBillingViews:
    def __init__(self, organization, request):
        self.organization = organization
        self.request = request
        self.billing_service = request.find_service(IBillingService, context=None)
        self.subscription_service = request.find_service(
            ISubscriptionService, context=None
        )
        self.organization_service = request.find_service(
            IOrganizationService, context=None
        )

    @property
    def customer_id(self):
        if self.organization.customer is None:
            customer = self.billing_service.create_customer(
                name=self.organization.customer_name(
                    self.request.registry.settings["site.name"]
                ),
                description=self.organization.description,
            )
            stripe_customer = self.subscription_service.add_stripe_customer(
                customer_id=customer["id"],
            )
            self.organization_service.add_organization_stripe_customer(
                organization_id=self.organization.id,
                stripe_customer_id=stripe_customer.id,
            )
            return customer["id"]
        return self.organization.customer.customer_id

    @property
    def price_id(self):
        # Get or create default subscription price with subscription service.
        default_subscription_price = (
            self.subscription_service.get_or_create_default_subscription_price()
        )
        # Synchronize product and price with billing service.
        self.billing_service.sync_product(
            default_subscription_price.subscription_product
        )
        self.billing_service.sync_price(default_subscription_price)
        return default_subscription_price.price_id

    @property
    def return_url(self):
        return urljoin(
            self.request.application_url,
            self.request.GET.get(
                "next", self.request.route_path("manage.organizations")
            ),
        )

    def create_subscription(self):
        # Create checkout session.
        checkout_session = self.billing_service.create_checkout_session(
            customer_id=self.customer_id,
            price_ids=[self.price_id],
            success_url=self.return_url,
            cancel_url=self.return_url,
        )
        create_subscription_url = checkout_session["url"]
        if isinstance(self.billing_service, MockStripeBillingService):
            # Use local mock of billing UI.
            create_subscription_url = self.request.route_path(
                "mock.billing.checkout-session",
                organization_name=self.organization.normalized_name,
            )
        return HTTPSeeOther(create_subscription_url)

    def manage_subscription(self):
        portal_session = self.billing_service.create_portal_session(
            customer_id=self.customer_id,
            return_url=self.return_url,
        )
        manage_subscription_url = portal_session["url"]
        if isinstance(self.billing_service, MockStripeBillingService):
            # Use local mock of billing UI.
            manage_subscription_url = self.request.route_path(
                "mock.billing.portal-session",
                organization_name=self.organization.normalized_name,
            )
        return HTTPSeeOther(manage_subscription_url)

    @view_config(
        route_name="manage.organization.activate_subscription",
        renderer="manage/organization/activate_subscription.html",
    )
    def activate_subscription(self):
        # We're not ready for companies to activate their own subscriptions yet.
        raise HTTPNotFound()
        # return {"organization": self.organization}

    @view_config(route_name="manage.organization.subscription")
    def create_or_manage_subscription(self):
        # Organizations must be enabled.
        if not self.request.organization_access:
            raise HTTPNotFound()

        if not self.organization.subscriptions:
            # Create subscription if there are no existing subscription.
            return self.create_subscription()
        else:
            # Manage subscription if there is an existing subscription.
            return self.manage_subscription()


@view_defaults(
    route_name="manage.organization.teams",
    context=Organization,
    renderer="manage/organization/teams.html",
    uses_session=True,
    require_active_organization=True,
    require_csrf=True,
    require_methods=False,
    permission="manage:team",
    has_translations=True,
    require_reauth=True,
)
class ManageOrganizationTeamsViews:
    def __init__(self, organization, request):
        self.organization = organization
        self.request = request
        self.organization_service = request.find_service(
            IOrganizationService, context=None
        )

    @property
    def default_response(self):
        return {
            "organization": self.organization,
            "create_team_form": CreateTeamForm(
                self.request.POST,
                organization_service=self.organization_service,
                organization_id=self.organization.id,
            ),
        }

    @view_config(request_method="GET", permission="view:organization")
    def manage_teams(self):
        return self.default_response

    @view_config(request_method="POST")
    def create_team(self):
        # Get and validate form from default response.
        default_response = self.default_response
        form = default_response["create_team_form"]
        if not form.validate():
            return default_response

        # Add team to organization.
        team = self.organization_service.add_team(
            organization_id=self.organization.id,
            name=form.name.data,
        )

        # Record events.
        self.organization.record_event(
            tag=EventTag.Organization.TeamCreate,
            request=self.request,
            additional={
                "created_by_user_id": str(self.request.user.id),
                "team_name": team.name,
            },
        )
        team.record_event(
            tag=EventTag.Team.TeamCreate,
            request=self.request,
            additional={
                "created_by_user_id": str(self.request.user.id),
            },
        )

        # Send notification emails.
        owner_and_manager_users = set(
            organization_owners(self.request, self.organization)
            + organization_managers(self.request, self.organization)
        )
        send_team_created_email(
            self.request,
            owner_and_manager_users,
            organization_name=self.organization.name,
            team_name=team.name,
        )

        # Display notification message.
        self.request.session.flash(
            f"Created team {team.name!r} in {self.organization.name!r}",
            queue="success",
        )

        # Refresh teams list.
        return HTTPSeeOther(self.request.path)


@view_defaults(
    route_name="manage.organization.projects",
    context=Organization,
    renderer="manage/organization/projects.html",
    uses_session=True,
    require_active_organization=True,
    require_csrf=True,
    require_methods=False,
    permission="manage:organization",
    has_translations=True,
    require_reauth=True,
)
class ManageOrganizationProjectsViews:
    def __init__(self, organization, request):
        self.organization = organization
        self.request = request
        self.user_service = request.find_service(IUserService, context=None)
        self.organization_service = request.find_service(
            IOrganizationService, context=None
        )
        self.project_factory = ProjectFactory(request)

    @property
    def active_projects(self):
        return self.organization.projects

    @property
    def default_response(self):
        active_projects = self.active_projects
        all_user_projects = user_projects(self.request)
        projects_owned = {
            project.name for project in all_user_projects["projects_owned"]
        }
        projects_sole_owned = {
            project.name for project in all_user_projects["projects_sole_owned"]
        }
        projects_requiring_2fa = {
            project.name for project in all_user_projects["projects_requiring_2fa"]
        }
        project_choices = {
            project.name
            for project in all_user_projects["projects_owned"]
            if not project.organization
        }
        project_factory = self.project_factory

        return {
            "organization": self.organization,
            "active_projects": active_projects,
            "projects_owned": projects_owned,
            "projects_sole_owned": projects_sole_owned,
            "projects_requiring_2fa": projects_requiring_2fa,
            "add_organization_project_form": AddOrganizationProjectForm(
                self.request.POST,
                project_choices=project_choices,
                project_factory=project_factory,
            ),
        }

    @view_config(request_method="GET", permission="view:organization")
    def manage_organization_projects(self):
        return self.default_response

    @view_config(request_method="POST", permission="add:project")
    def add_organization_project(self):
        # Get and validate form from default response.
        default_response = self.default_response
        form = default_response["add_organization_project_form"]
        if not form.validate():
            return default_response

        # Get existing project or add new project.
        if form.add_existing_project.data:
            # Get existing project.
            project = self.project_factory[form.existing_project_name.data]
            # Remove request user as individual project owner.
            role = (
                self.request.db.query(Role)
                .join(User)
                .filter(
                    Role.role_name == "Owner",
                    Role.project == project,
                    Role.user == self.request.user,
                )
                .first()
            )
            if role:
                self.request.db.delete(role)
                self.request.db.add(
                    JournalEntry(
                        name=project.name,
                        action=f"remove {role.role_name} {role.user.username}",
                        submitted_by=self.request.user,
                    )
                )
                project.record_event(
                    tag=EventTag.Project.RoleRemove,
                    request=self.request,
                    additional={
                        "submitted_by": self.request.user.username,
                        "role_name": role.role_name,
                        "target_user": role.user.username,
                    },
                )
                role.user.record_event(
                    tag=EventTag.Account.RoleRemove,
                    request=self.request,
                    additional={
                        "submitted_by": self.request.user.username,
                        "project_name": project.name,
                        "role_name": role.role_name,
                    },
                )
        else:
            # Validate new project name.
            try:
                validate_project_name(form.new_project_name.data, self.request)
            except HTTPException as exc:
                form.new_project_name.errors.append(exc.detail)
                return default_response

            # Add new project.
            # Note that we pass `creator_is_owner=False`, since the project being
            # created is controlled by the organization and not the user creating it.
            project_service = self.request.find_service(IProjectService)
            project = project_service.create_project(
                form.new_project_name.data,
                self.request.user,
                request=self.request,
                creator_is_owner=False,
                ratelimited=False,
            )

        # Add project to organization.
        self.organization_service.add_organization_project(
            organization_id=self.organization.id,
            project_id=project.id,
        )

        # Record events.
        self.organization.record_event(
            tag=EventTag.Organization.OrganizationProjectAdd,
            request=self.request,
            additional={
                "submitted_by_user_id": str(self.request.user.id),
                "project_name": project.name,
            },
        )
        project.record_event(
            tag=EventTag.Project.OrganizationProjectAdd,
            request=self.request,
            additional={
                "submitted_by_user_id": str(self.request.user.id),
                "organization_name": self.organization.name,
            },
        )

        # Send notification emails.
        owner_users = set(
            organization_owners(self.request, self.organization)
            + project_owners(self.request, project)
        )
        send_organization_project_added_email(
            self.request,
            owner_users,
            organization_name=self.organization.name,
            project_name=project.name,
        )

        # Display notification message.
        self.request.session.flash(
            f"Added the project {project.name!r} to {self.organization.name!r}",
            queue="success",
        )

        # Refresh projects list.
        return HTTPSeeOther(self.request.path)


def _send_organization_invitation(request, organization, role_name, user):
    organization_service = request.find_service(IOrganizationService, context=None)
    token_service = request.find_service(ITokenService, name="email")

    existing_role = organization_service.get_organization_role_by_user(
        organization.id, user.id
    )
    organization_invite = organization_service.get_organization_invite_by_user(
        organization.id, user.id
    )
    # Cover edge case where invite is invalid but task
    # has not updated invite status
    try:
        invite_token = token_service.loads(organization_invite.token)
    except (TokenExpired, AttributeError):
        invite_token = None

    if existing_role:
        request.session.flash(
            request._(
                "User '${username}' already has ${role_name} role for organization",
                mapping={
                    "username": user.username,
                    "role_name": existing_role.role_name.value,
                },
            ),
            queue="error",
        )
    elif user.primary_email is None or not user.primary_email.verified:
        request.session.flash(
            request._(
                "User '${username}' does not have a verified primary email "
                "address and cannot be added as a ${role_name} for organization",
                mapping={"username": user.username, "role_name": role_name},
            ),
            queue="error",
        )
    elif (
        organization_invite
        and organization_invite.invite_status == OrganizationInvitationStatus.Pending
        and invite_token
    ):
        request.session.flash(
            request._(
                "User '${username}' already has an active invite. "
                "Please try again later.",
                mapping={"username": user.username},
            ),
            queue="error",
        )
    else:
        invite_token = token_service.dumps(
            {
                "action": "email-organization-role-verify",
                "desired_role": role_name,
                "user_id": user.id,
                "organization_id": organization.id,
                "submitter_id": request.user.id,
            }
        )
        if organization_invite:
            organization_invite.invite_status = OrganizationInvitationStatus.Pending
            organization_invite.token = invite_token
        else:
            organization_service.add_organization_invite(
                organization_id=organization.id,
                user_id=user.id,
                invite_token=invite_token,
            )
        organization.record_event(
            tag=EventTag.Organization.OrganizationRoleInvite,
            request=request,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "role_name": role_name,
                "target_user_id": str(user.id),
            },
        )
        user.record_event(
            tag=EventTag.Account.OrganizationRoleInvite,
            request=request,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "organization_name": organization.name,
                "role_name": role_name,
            },
        )
        owner_users = set(organization_owners(request, organization))
        send_organization_member_invited_email(
            request,
            owner_users,
            user=user,
            desired_role=role_name,
            initiator_username=request.user.username,
            organization_name=organization.name,
            email_token=invite_token,
            token_age=token_service.max_age,
        )
        send_organization_role_verification_email(
            request,
            user,
            desired_role=role_name,
            initiator_username=request.user.username,
            organization_name=organization.name,
            email_token=invite_token,
            token_age=token_service.max_age,
        )
        request.session.flash(
            request._(
                "Invitation sent to '${username}'",
                mapping={"username": user.username},
            ),
            queue="success",
        )


@view_config(
    route_name="manage.organization.roles",
    context=Organization,
    renderer="manage/organization/roles.html",
    uses_session=True,
    require_active_organization=True,
    require_methods=False,
    permission="view:organization",
    has_translations=True,
    require_reauth=True,
)
def manage_organization_roles(
    organization, request, _form_class=CreateOrganizationRoleForm
):
    organization_service = request.find_service(IOrganizationService, context=None)
    user_service = request.find_service(IUserService, context=None)
    form = _form_class(
        request.POST,
        orgtype=organization.orgtype,
        organization_service=organization_service,
        user_service=user_service,
    )

    if request.method == "POST" and form.validate():
        username = form.username.data
        role_name = form.role_name.data
        userid = user_service.find_userid(username)
        user = user_service.get_user(userid)

        _send_organization_invitation(request, organization, role_name.value, user)

        return HTTPSeeOther(request.path)

    roles = set(organization_service.get_organization_roles(organization.id))
    invitations = set(organization_service.get_organization_invites(organization.id))

    return {
        "organization": organization,
        "roles": roles,
        "invitations": invitations,
        "form": form,
        "organizations_with_sole_owner": list(
            organization.name
            for organization in user_organizations(request)[
                "organizations_with_sole_owner"
            ]
        ),
    }


@view_config(
    route_name="manage.organization.resend_invite",
    context=Organization,
    uses_session=True,
    require_active_organization=True,
    require_methods=["POST"],
    permission="manage:organization",
    has_translations=True,
)
def resend_organization_invitation(organization, request):
    organization_service = request.find_service(IOrganizationService, context=None)
    user_service = request.find_service(IUserService, context=None)
    token_service = request.find_service(ITokenService, name="email")
    user = user_service.get_user(request.POST["user_id"])

    _next = request.route_path(
        "manage.organization.roles",
        organization_name=organization.normalized_name,
    )

    organization_invite = organization_service.get_organization_invite_by_user(
        organization.id, user.id
    )
    if organization_invite is None:
        request.session.flash(
            request._("Could not find organization invitation."), queue="error"
        )
        return HTTPSeeOther(_next)

    # Note: underlying itsdangerous method of "token_service.unsafe_load_payload never
    # fails, it just returns None if the payload is not deserializable. Our wrapper
    # does at least validate that the signature was valid.
    token_data = token_service.unsafe_load_payload(organization_invite.token)
    if token_data is None:
        request.session.flash(
            request._("Organization invitation could not be re-sent."), queue="error"
        )
        return HTTPSeeOther(_next)

    role_name = token_data.get("desired_role")
    _send_organization_invitation(
        request, organization, role_name, organization_invite.user
    )

    return HTTPSeeOther(_next)


@view_config(
    route_name="manage.organization.revoke_invite",
    context=Organization,
    uses_session=True,
    require_active_organization=True,
    require_methods=["POST"],
    permission="manage:organization",
    has_translations=True,
)
def revoke_organization_invitation(organization, request):
    organization_service = request.find_service(IOrganizationService, context=None)
    user_service = request.find_service(IUserService, context=None)
    token_service = request.find_service(ITokenService, name="email")
    user = user_service.get_user(request.POST["user_id"])

    organization_invite = organization_service.get_organization_invite_by_user(
        organization.id, user.id
    )
    if organization_invite is None:
        request.session.flash(
            request._("Could not find organization invitation."), queue="error"
        )
        return HTTPSeeOther(
            request.route_path(
                "manage.organization.roles",
                organization_name=organization.normalized_name,
            )
        )

    organization_service.delete_organization_invite(organization_invite.id)

    try:
        token_data = token_service.loads(organization_invite.token)
    except TokenExpired:
        request.session.flash(
            request._(
                "Expired invitation for '${username}' deleted.",
                mapping={"username": user.username},
            ),
            queue="success",
        )
        return HTTPSeeOther(
            request.route_path(
                "manage.organization.roles",
                organization_name=organization.normalized_name,
            )
        )
    role_name = token_data.get("desired_role")

    organization.record_event(
        tag=EventTag.Organization.OrganizationRoleRevokeInvite,
        request=request,
        additional={
            "submitted_by_user_id": str(request.user.id),
            "role_name": role_name,
            "target_user_id": str(user.id),
        },
    )
    user.record_event(
        tag=EventTag.Account.OrganizationRoleRevokeInvite,
        request=request,
        additional={
            "submitted_by_user_id": str(request.user.id),
            "organization_name": organization.name,
            "role_name": role_name,
        },
    )

    owner_users = set(organization_owners(request, organization))
    send_organization_member_invite_canceled_email(
        request,
        owner_users,
        user=user,
        organization_name=organization.name,
    )
    send_canceled_as_invited_organization_member_email(
        request,
        user,
        organization_name=organization.name,
    )

    request.session.flash(
        request._(
            "Invitation revoked from '${username}'.",
            mapping={"username": user.username},
        ),
        queue="success",
    )

    return HTTPSeeOther(
        request.route_path(
            "manage.organization.roles", organization_name=organization.normalized_name
        )
    )


@view_config(
    route_name="manage.organization.change_role",
    context=Organization,
    uses_session=True,
    require_active_organization=True,
    require_methods=["POST"],
    permission="manage:organization",
    has_translations=True,
    require_reauth=True,
)
def change_organization_role(
    organization, request, _form_class=ChangeOrganizationRoleForm
):
    form = _form_class(request.POST, orgtype=organization.orgtype)

    if form.validate():
        organization_service = request.find_service(IOrganizationService, context=None)
        role_id = request.POST["role_id"]
        role = organization_service.get_organization_role(role_id)
        if not role or role.organization_id != organization.id:
            request.session.flash("Could not find member", queue="error")
        elif role.role_name == OrganizationRoleType.Owner and role.user == request.user:
            request.session.flash("Cannot remove yourself as Owner", queue="error")
        else:
            role.role_name = form.role_name.data

            owner_users = set(organization_owners(request, organization))
            # Don't send owner notification email to new user
            # if they are now an owner
            owner_users.discard(role.user)

            send_organization_member_role_changed_email(
                request,
                owner_users,
                user=role.user,
                submitter=request.user,
                organization_name=organization.name,
                role=role.role_name.value,
            )

            send_role_changed_as_organization_member_email(
                request,
                role.user,
                submitter=request.user,
                organization_name=organization.name,
                role=role.role_name.value,
            )

            organization.record_event(
                tag=EventTag.Organization.OrganizationRoleChange,
                request=request,
                additional={
                    "submitted_by_user_id": str(request.user.id),
                    "role_name": form.role_name.data,
                    "target_user_id": str(role.user.id),
                },
            )
            role.user.record_event(
                tag=EventTag.Account.OrganizationRoleChange,
                request=request,
                additional={
                    "submitted_by_user_id": str(request.user.id),
                    "organization_name": organization.name,
                    "role_name": form.role_name.data,
                },
            )

            request.session.flash("Changed role", queue="success")

    return HTTPSeeOther(
        request.route_path(
            "manage.organization.roles", organization_name=organization.normalized_name
        )
    )


@view_config(
    route_name="manage.organization.delete_role",
    context=Organization,
    uses_session=True,
    require_active_organization=True,
    require_methods=["POST"],
    permission="view:organization",
    has_translations=True,
    require_reauth=True,
)
def delete_organization_role(organization, request):
    organization_service = request.find_service(IOrganizationService, context=None)
    role_id = request.POST["role_id"]
    role = organization_service.get_organization_role(role_id)
    organizations_sole_owned = {
        organization.id
        for organization in user_organizations(request)["organizations_with_sole_owner"]
    }
    is_sole_owner = organization.id in organizations_sole_owned

    if not role or role.organization_id != organization.id:
        request.session.flash("Could not find member", queue="error")
    elif (
        not request.has_permission("manage:organization") and role.user != request.user
    ):
        request.session.flash(
            "Cannot remove other people from the organization", queue="error"
        )
    elif (
        role.role_name == OrganizationRoleType.Owner
        and role.user == request.user
        and is_sole_owner
    ):
        request.session.flash("Cannot remove yourself as Sole Owner", queue="error")
    else:
        organization_service.delete_organization_role(role.id)
        organization.record_event(
            tag=EventTag.Organization.OrganizationRoleRemove,
            request=request,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "role_name": role.role_name.value,
                "target_user_id": str(role.user.id),
            },
        )
        role.user.record_event(
            tag=EventTag.Account.OrganizationRoleRemove,
            request=request,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "organization_name": organization.name,
                "role_name": role.role_name.value,
            },
        )

        owner_users = set(organization_owners(request, organization))
        # Don't send owner notification email to new user
        # if they are now an owner
        owner_users.discard(role.user)

        send_organization_member_removed_email(
            request,
            owner_users,
            user=role.user,
            submitter=request.user,
            organization_name=organization.name,
        )

        send_removed_as_organization_member_email(
            request,
            role.user,
            submitter=request.user,
            organization_name=organization.name,
        )

        request.session.flash("Removed from organization", queue="success")

    if role and role.user == request.user:
        # User removed self from organization.
        return HTTPSeeOther(request.route_path("manage.organizations"))
    else:
        return HTTPSeeOther(
            request.route_path(
                "manage.organization.roles",
                organization_name=organization.normalized_name,
            )
        )


@view_config(
    route_name="manage.organization.history",
    context=Organization,
    renderer="manage/organization/history.html",
    uses_session=True,
    permission="manage:organization",
    has_translations=True,
)
def manage_organization_history(organization, request):
    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.")

    events_query = (
        request.db.query(Organization.Event)
        .join(Organization.Event.source)
        .filter(Organization.Event.source_id == organization.id)
        .order_by(Organization.Event.time.desc())
        .order_by(Organization.Event.tag.desc())
    )

    events = SQLAlchemyORMPage(
        events_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    if events.page_count and page_num > events.page_count:
        raise HTTPNotFound

    user_service = request.find_service(IUserService, context=None)

    return {
        "events": events,
        "get_user": user_service.get_user,
        "organization": organization,
    }


@view_config(
    route_name="manage.project.remove_organization_project",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission="manage:project",
    has_translations=True,
    require_reauth=True,
)
def remove_organization_project(project, request):
    if not request.organization_access:
        request.session.flash("Organizations are disabled", queue="error")
        return HTTPSeeOther(
            request.route_path("manage.project.settings", project_name=project.name)
        )

    if (
        # Check that user has permission to remove projects from organization.
        (project.organization and request.user not in project.organization.owners)
        # Check that project has an individual owner.
        or not project_owners(request, project)
    ):
        request.session.flash(
            (
                "Could not remove project from organization - "
                "you do not have the required permissions"
            ),
            queue="error",
        )
        return HTTPSeeOther(
            request.route_path("manage.project.settings", project_name=project.name)
        )

    confirm_project(
        project,
        request,
        fail_route="manage.project.settings",
        field_name="confirm_remove_organization_project_name",
        error_message="Could not remove project from organization",
    )

    # Remove project from current organization.
    organization_service = request.find_service(IOrganizationService, context=None)
    if organization := project.organization:
        organization_service.delete_organization_project(organization.id, project.id)
        organization.record_event(
            tag=EventTag.Organization.OrganizationProjectRemove,
            request=request,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "project_name": project.name,
            },
        )
        project.record_event(
            tag=EventTag.Project.OrganizationProjectRemove,
            request=request,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "organization_name": organization.name,
            },
        )
        # Send notification emails.
        owner_users = set(
            organization_owners(request, organization)
            + project_owners(request, project)
        )
        send_organization_project_removed_email(
            request,
            owner_users,
            organization_name=organization.name,
            project_name=project.name,
        )
        # Display notification message.
        request.session.flash(
            f"Removed the project {project.name!r} from {organization.name!r}",
            queue="success",
        )

        return HTTPSeeOther(
            request.route_path(
                "manage.organization.projects",
                organization_name=organization.normalized_name,
            )
        )

    request.session.flash(
        ("Could not remove project from organization - no organization found"),
        queue="error",
    )
    return HTTPSeeOther(
        request.route_path("manage.project.settings", project_name=project.name)
    )


@view_config(
    route_name="manage.project.transfer_organization_project",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission="manage:project",
    has_translations=True,
    require_reauth=True,
)
def transfer_organization_project(project, request):
    if not request.organization_access:
        request.session.flash("Organizations are disabled", queue="error")
        return HTTPSeeOther(
            request.route_path("manage.project.settings", project_name=project.name)
        )

    # Check that user has permission to remove projects from organization.
    if project.organization and request.user not in project.organization.owners:
        request.session.flash(
            "Could not transfer project - you do not have the required permissions",
            queue="error",
        )
        return HTTPSeeOther(
            request.route_path("manage.project.settings", project_name=project.name)
        )

    confirm_project(
        project,
        request,
        fail_route="manage.project.settings",
        field_name="confirm_transfer_organization_project_name",
        error_message="Could not transfer project",
    )

    all_user_organizations = user_organizations(request)
    active_organizations_owned = {
        organization.name
        for organization in all_user_organizations["organizations_owned"]
        if organization.is_active
    }
    active_organizations_managed = {
        organization.name
        for organization in all_user_organizations["organizations_managed"]
        if organization.is_active
    }
    current_organization = (
        {project.organization.name} if project.organization else set()
    )
    organization_choices = (
        active_organizations_owned | active_organizations_managed
    ) - current_organization

    form = TransferOrganizationProjectForm(
        request.POST,
        organization_choices=organization_choices,
    )

    if not form.validate():
        for error_list in form.errors.values():
            for error in error_list:
                request.session.flash(error, queue="error")
        return HTTPSeeOther(
            request.route_path("manage.project.settings", project_name=project.name)
        )

    # Remove request user as individual project owner.
    role = (
        request.db.query(Role)
        .join(User)
        .filter(
            Role.role_name == "Owner",
            Role.project == project,
            Role.user == request.user,
        )
        .first()
    )
    if role:
        request.db.delete(role)
        request.db.add(
            JournalEntry(
                name=project.name,
                action=f"remove {role.role_name} {role.user.username}",
                submitted_by=request.user,
            )
        )
        project.record_event(
            tag=EventTag.Project.RoleRemove,
            request=request,
            additional={
                "submitted_by": request.user.username,
                "role_name": role.role_name,
                "target_user": role.user.username,
            },
        )

    # Remove project from current organization.
    organization_service = request.find_service(IOrganizationService, context=None)
    if organization := project.organization:
        organization_service.delete_organization_project(organization.id, project.id)
        organization.record_event(
            tag=EventTag.Organization.OrganizationProjectRemove,
            request=request,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "project_name": project.name,
            },
        )
        project.record_event(
            tag=EventTag.Project.OrganizationProjectRemove,
            request=request,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "organization_name": organization.name,
            },
        )
        # Send notification emails.
        owner_users = set(
            organization_owners(request, organization)
            + project_owners(request, project)
        )
        send_organization_project_removed_email(
            request,
            owner_users,
            organization_name=organization.name,
            project_name=project.name,
        )

        # Mark Organization as dirty, so purges will happen
        orm.attributes.flag_dirty(organization)

    # Add project to selected organization.
    organization = organization_service.get_organization_by_name(form.organization.data)
    organization_service.add_organization_project(organization.id, project.id)
    organization.record_event(
        tag=EventTag.Organization.OrganizationProjectAdd,
        request=request,
        additional={
            "submitted_by_user_id": str(request.user.id),
            "project_name": project.name,
        },
    )
    project.record_event(
        tag=EventTag.Project.OrganizationProjectAdd,
        request=request,
        additional={
            "submitted_by_user_id": str(request.user.id),
            "organization_name": organization.name,
        },
    )

    # Mark Organization as dirty, so purges will happen
    orm.attributes.flag_dirty(organization)

    # Send notification emails.
    owner_users = set(
        organization_owners(request, organization) + project_owners(request, project)
    )
    send_organization_project_added_email(
        request,
        owner_users,
        organization_name=organization.name,
        project_name=project.name,
    )

    request.session.flash(
        f"Transferred the project {project.name!r} to {organization.name!r}",
        queue="success",
    )

    return HTTPSeeOther(
        request.route_path("manage.project.settings", project_name=project.name)
    )
