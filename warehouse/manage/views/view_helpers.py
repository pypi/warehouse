# SPDX-License-Identifier: Apache-2.0

"""
Shared view-layer helpers, preventing circular imports.

Originally scoped to `manage/views`, some helpers here (e.g.
`add_organization_project_and_notify`) are also used by `admin/views`.
"""

from __future__ import annotations

import typing

from sqlalchemy import func

from warehouse.accounts.models import User
from warehouse.email import send_organization_project_added_email
from warehouse.events.tags import EventTag
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import (
    Organization,
    OrganizationRole,
    OrganizationRoleType,
    Team,
    TeamProjectRole,
    TeamProjectRoleType,
    TeamRole,
)
from warehouse.packaging import Project, Role
from warehouse.subscriptions import IBillingService
from warehouse.subscriptions.models import StripeSubscriptionStatus

if typing.TYPE_CHECKING:
    from pyramid.request import Request


def project_owners(request, project):
    """Return all users who are owners of the project."""
    return project.owners


def organization_owners(request: Request, organization: Organization) -> list[User]:
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


def deactivate_organization_for_owner_removal(
    request: Request,
    organization: Organization,
    *,
    target_user: User,
    reason: str,
) -> None:
    """Cancel billing, deactivate, and log an organization whose sole owner is
    being removed.
    """
    # Stripe raises when canceling a subscription already in a terminal
    # state, and warehouse retains those subscription rows.
    cancelable_subscriptions = [
        subscription
        for subscription in organization.subscriptions
        if subscription.status
        not in (
            StripeSubscriptionStatus.Canceled.value,
            StripeSubscriptionStatus.IncompleteExpired.value,
        )
    ]
    if cancelable_subscriptions:
        billing_service = request.find_service(IBillingService, context=None)
        for subscription in cancelable_subscriptions:
            billing_service.cancel_subscription(subscription.subscription_id)

    organization.record_event(
        tag=EventTag.Organization.OrganizationRoleRemove,
        request=request,
        additional={
            "submitted_by_user_id": str(request.user.id),
            "role_name": OrganizationRoleType.Owner.value,
            "target_user_id": str(target_user.id),
            "reason": reason,
        },
    )
    organization.is_active = False


def add_organization_project_and_notify(
    request: Request,
    organization: Organization,
    project: Project,
    *,
    link: bool = True,
) -> None:
    """Associate ``project`` with ``organization``, record events, and notify owners.

    Shared by the manage-side "add project to organization" and "transfer
    project to organization" flows and the admin prohibited-name release flow.

    Pass ``link=False`` when the ``OrganizationProject`` association was
    already created by the caller (e.g. ``create_project(organization_id=...)``
    links inline), so it isn't linked twice.
    """
    if link:
        organization_service = request.find_service(IOrganizationService, context=None)
        organization_service.add_organization_project(
            organization_id=organization.id, project_id=project.id
        )

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

    owner_users = set(
        organization_owners(request, organization) + project_owners(request, project)
    )
    send_organization_project_added_email(
        request,
        owner_users,
        organization_name=organization.name,
        project_name=project.name,
    )


def user_organizations(request):
    """Return all the organizations for which the user has a privileged role."""
    organizations_managed = (
        request.db.query(Organization.id)
        .join(OrganizationRole.organization)
        .filter(
            OrganizationRole.role_name == OrganizationRoleType.Manager,
            OrganizationRole.user == request.user,
        )
        .subquery()
    )
    organizations_owned = (
        request.db.query(Organization.id)
        .join(OrganizationRole.organization)
        .filter(
            OrganizationRole.role_name == OrganizationRoleType.Owner,
            OrganizationRole.user == request.user,
        )
        .subquery()
    )
    organizations_billing = (
        request.db.query(Organization.id)
        .join(OrganizationRole.organization)
        .filter(
            OrganizationRole.role_name == OrganizationRoleType.BillingManager,
            OrganizationRole.user == request.user,
        )
        .subquery()
    )
    organizations_with_sole_owner = (
        request.db.query(OrganizationRole.organization_id)
        .join(organizations_owned)
        .filter(OrganizationRole.role_name == "Owner")
        .group_by(OrganizationRole.organization_id)
        .having(func.count(OrganizationRole.organization_id) == 1)
        .subquery()
    )
    return {
        "organizations_owned": (
            request.db.query(Organization)
            .join(organizations_owned, Organization.id == organizations_owned.c.id)
            .order_by(Organization.name)
            .all()
        ),
        "organizations_managed": (
            request.db.query(Organization)
            .join(organizations_managed, Organization.id == organizations_managed.c.id)
            .order_by(Organization.name)
            .all()
        ),
        "organizations_billing": (
            request.db.query(Organization)
            .join(organizations_billing, Organization.id == organizations_billing.c.id)
            .order_by(Organization.name)
            .all()
        ),
        "organizations_with_sole_owner": (
            request.db.query(Organization)
            .join(
                organizations_with_sole_owner,
                Organization.id == organizations_with_sole_owner.c.organization_id,
            )
            .order_by(Organization.name)
            .all()
        ),
    }


def user_projects(request):
    """Return all the projects for which the user is a sole owner"""
    projects_owned = (
        request.db.query(Project.id.label("id"))
        .join(Role.project)
        .filter(Role.role_name == "Owner", Role.user == request.user)
    )

    projects_collaborator = (
        request.db.query(Project.id)
        .join(Role.project)
        .filter(Role.user == request.user)
    )

    with_sole_owner = (
        # Select projects having just one owner.
        request.db.query(Role.project_id)
        .join(projects_owned.subquery())
        .filter(Role.role_name == "Owner")
        .group_by(Role.project_id)
        .having(func.count(Role.project_id) == 1)
        # Except projects owned by an organization.
        .join(Role.project)
        .filter(~Project.organization.has())
    )

    organizations_owned = (
        request.db.query(Organization.id)
        .join(OrganizationRole.organization)
        .filter(
            OrganizationRole.role_name == OrganizationRoleType.Owner,
            OrganizationRole.user == request.user,
        )
        .subquery()
    )

    organizations_with_sole_owner = (
        request.db.query(OrganizationRole.organization_id)
        .join(organizations_owned)
        .filter(OrganizationRole.role_name == "Owner")
        .group_by(OrganizationRole.organization_id)
        .having(func.count(OrganizationRole.organization_id) == 1)
        .subquery()
    )

    teams = (
        request.db.query(Team.id)
        .join(TeamRole.team)
        .filter(TeamRole.user == request.user)
        .subquery()
    )

    projects_owned = projects_owned.union(
        request.db.query(Project.id.label("id"))
        .join(Organization.projects)
        .join(organizations_owned, Organization.id == organizations_owned.c.id),
        request.db.query(Project.id.label("id"))
        .join(TeamProjectRole.project)
        .join(teams, TeamProjectRole.team_id == teams.c.id)
        .filter(TeamProjectRole.role_name == TeamProjectRoleType.Owner),
    )

    with_sole_owner = with_sole_owner.union(
        # Select projects where organization has only one owner.
        request.db.query(Project.id)
        .join(Organization.projects)
        .join(
            organizations_with_sole_owner,
            Organization.id == organizations_with_sole_owner.c.organization_id,
        )
        # Except projects with any other individual owners.
        .filter(
            ~Project.roles.any(
                (Role.role_name == "Owner") & (Role.user_id != request.user.id)
            )
        )
    )

    projects_owned = projects_owned.subquery()
    projects_collaborator = projects_collaborator.subquery()
    with_sole_owner = with_sole_owner.subquery()

    return {
        "projects_owned": (
            request.db.query(Project)
            .join(projects_owned, Project.id == projects_owned.c.id)
            .order_by(Project.name)
            .all()
        ),
        "projects_sole_owned": (
            request.db.query(Project).join(with_sole_owner).order_by(Project.name).all()
        ),
    }
