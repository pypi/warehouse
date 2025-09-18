# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse.admin.views import core as views

from ....common.db.organizations import (
    OrganizationApplicationFactory,
    OrganizationFactory,
    OrganizationProjectFactory,
    OrganizationRoleFactory,
    OrganizationStripeSubscriptionFactory,
)
from ....common.db.packaging import ProjectObservationFactory


class TestDashboard:
    def test_dashboard(self, db_request):
        company_orgs = OrganizationFactory.create_batch(7, orgtype="Company")
        community_orgs = OrganizationFactory.create_batch(11, orgtype="Community")
        OrganizationApplicationFactory.create_batch(5, orgtype="Company")
        OrganizationApplicationFactory.create_batch(3, orgtype="Community")

        # Create projects for some organizations
        # 3 Company orgs with projects, 5 Community orgs with projects
        for organization in company_orgs[:3]:
            OrganizationProjectFactory.create(organization=organization)
        for organization in community_orgs[:5]:
            OrganizationProjectFactory.create(organization=organization)

        # Add members to organizations (for testing orgs with multiple members)
        # 4 Company orgs with >1 member, 6 Community orgs with >1 member
        for organization in company_orgs[:4]:
            OrganizationRoleFactory.create_batch(2, organization=organization)
        for organization in community_orgs[:6]:
            OrganizationRoleFactory.create_batch(2, organization=organization)

        # Add single members to some orgs (shouldn't count in multiple members)
        for organization in company_orgs[4:6]:
            OrganizationRoleFactory.create(organization=organization)
        for organization in community_orgs[6:9]:
            OrganizationRoleFactory.create(organization=organization)

        # Create subscriptions for some company orgs
        for organization in company_orgs[:3]:
            OrganizationStripeSubscriptionFactory.create(organization=organization)

        db_request.user = pretend.stub()
        db_request.has_permission = pretend.call_recorder(lambda perm: False)

        assert views.dashboard(db_request) == {
            "malware_reports_count": None,
            "organizations_count": {"Total": 18, "Community": 11, "Company": 7},
            "organization_applications_count": {"Total": 8, "submitted": 8},
            "active_company_organizations": 3,
            "active_company_organization_users": 6,  # 3 orgs * 2 members
            "orgs_with_projects": {"Total": 8, "Community": 5, "Company": 3},
            "orgs_with_multiple_members": {"Total": 10, "Community": 6, "Company": 4},
        }

        assert db_request.has_permission.calls == [
            pretend.call(views.Permissions.AdminObservationsRead),
        ]

    def test_dashboard_with_permission_and_observation(self, db_request):
        """Test that the dashboard view returns the correct data when the user has the
        required permission and there are multiple Observations in the database."""
        ProjectObservationFactory.create(kind="is_malware")
        ProjectObservationFactory.create(kind="is_malware", actions={"foo": "bar"})
        ProjectObservationFactory.create(kind="is_malware", related=None)
        ProjectObservationFactory.create(kind="something_else")
        db_request.user = pretend.stub()
        db_request.has_permission = pretend.call_recorder(lambda perm: True)

        assert views.dashboard(db_request) == {
            "malware_reports_count": 1,
            "organizations_count": {"Total": 0},
            "organization_applications_count": {"Total": 0},
            "active_company_organizations": 0,
            "active_company_organization_users": 0,
            "orgs_with_projects": {"Total": 0},
            "orgs_with_multiple_members": {"Total": 0},
        }
        assert db_request.has_permission.calls == [
            pretend.call(views.Permissions.AdminObservationsRead),
        ]
