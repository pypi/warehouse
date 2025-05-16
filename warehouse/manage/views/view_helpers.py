# SPDX-License-Identifier: Apache-2.0

"""
Helper functions for `manage/views`, preventing circular imports.
"""

from sqlalchemy import func

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


def project_owners(request, project):
    """Return all users who are owners of the project."""
    return project.owners


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
