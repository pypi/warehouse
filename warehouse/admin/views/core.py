# SPDX-License-Identifier: Apache-2.0

from pyramid.view import view_config
from sqlalchemy import distinct, func

from warehouse.authnz import Permissions
from warehouse.observations.models import Observation, ObservationKind
from warehouse.organizations.models import (
    Organization,
    OrganizationApplication,
    OrganizationProject,
    OrganizationRole,
    OrganizationType,
)
from warehouse.subscriptions.models import StripeSubscription, StripeSubscriptionStatus


@view_config(
    route_name="admin.dashboard",
    renderer="warehouse.admin:templates/admin/dashboard.html",
    permission=Permissions.AdminDashboardRead,
    uses_session=True,
)
def dashboard(request):
    if request.has_permission(Permissions.AdminObservationsRead):
        # Count how many Malware Project Observations are in the database
        malware_reports_count = (
            request.db.query(func.count(Observation.id)).filter(
                Observation.kind == ObservationKind.IsMalware.value[0],
                Observation.related_id.is_not(None),  # Project is not removed
                Observation.actions == {},  # No actions have been taken
            )
        ).scalar()
    else:
        malware_reports_count = None

    organizations_count = (
        request.db.query(Organization.orgtype, func.count(Organization.id))
        .group_by(Organization.orgtype)
        .all()
    )
    organizations_count = {k.value: v for k, v in organizations_count}
    organizations_count["Total"] = sum([v for k, v in organizations_count.items()])

    organization_applications_count = (
        request.db.query(
            OrganizationApplication.status, func.count(OrganizationApplication.id)
        )
        .group_by(OrganizationApplication.status)
        .all()
    )
    organization_applications_count = {
        k.value: v for k, v in organization_applications_count
    }
    organization_applications_count["Total"] = sum(
        [v for k, v in organization_applications_count.items()]
    )

    active_company_organizations = (
        request.db.query(func.count(Organization.id))
        .filter(Organization.orgtype == OrganizationType.Company)
        .filter(
            Organization.subscriptions.any(
                StripeSubscription.status.in_(
                    (
                        StripeSubscriptionStatus.Active.value,
                        StripeSubscriptionStatus.Trialing.value,
                    )
                )
            )
        )
        .scalar()
    )
    active_company_organization_users = (
        request.db.query(func.count(OrganizationRole.id))
        .join(Organization)
        .filter(Organization.orgtype == OrganizationType.Company)
        .filter(
            Organization.subscriptions.any(
                StripeSubscription.status.in_(
                    (
                        StripeSubscriptionStatus.Active.value,
                        StripeSubscriptionStatus.Trialing.value,
                    )
                )
            )
        )
        .scalar()
    )

    # New statistics: Organizations with projects by type
    orgs_with_projects = (
        request.db.query(
            Organization.orgtype,
            func.count(distinct(Organization.id)).label("org_count"),
        )
        .join(
            OrganizationProject, Organization.id == OrganizationProject.organization_id
        )
        .group_by(Organization.orgtype)
        .all()
    )
    orgs_with_projects = {k.value: v for k, v in orgs_with_projects}
    orgs_with_projects["Total"] = sum(orgs_with_projects.values())

    # Organizations with more than 1 member by type
    orgs_with_members_subquery = (
        request.db.query(
            Organization.orgtype,
            Organization.id,
            func.count(OrganizationRole.user_id).label("members"),
        )
        .join(OrganizationRole, Organization.id == OrganizationRole.organization_id)
        .group_by(Organization.id, Organization.orgtype)
        .subquery()
    )

    orgs_with_multiple_members = (
        request.db.query(
            orgs_with_members_subquery.c.orgtype,
            func.count(orgs_with_members_subquery.c.id).label("org_count"),
        )
        .filter(orgs_with_members_subquery.c.members > 1)
        .group_by(orgs_with_members_subquery.c.orgtype)
        .all()
    )
    orgs_with_multiple_members = {k.value: v for k, v in orgs_with_multiple_members}
    orgs_with_multiple_members["Total"] = sum(orgs_with_multiple_members.values())

    return {
        "malware_reports_count": malware_reports_count,
        "organizations_count": organizations_count,
        "organization_applications_count": organization_applications_count,
        "active_company_organizations": active_company_organizations,
        "active_company_organization_users": active_company_organization_users,
        "orgs_with_projects": orgs_with_projects,
        "orgs_with_multiple_members": orgs_with_multiple_members,
    }
