# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse.admin.views import core as views

from ....common.db.organizations import (
    OrganizationApplicationFactory,
    OrganizationFactory,
    OrganizationRoleFactory,
    OrganizationStripeSubscriptionFactory,
)
from ....common.db.packaging import ProjectObservationFactory


class TestDashboard:
    def test_dashboard(self, db_request):
        company_orgs = OrganizationFactory.create_batch(7, orgtype="Company")
        OrganizationFactory.create_batch(11, orgtype="Community")
        OrganizationApplicationFactory.create_batch(5, orgtype="Company")
        OrganizationApplicationFactory.create_batch(3, orgtype="Community")

        for organization in company_orgs:
            OrganizationRoleFactory.create_batch(2, organization=organization)

        for organization in company_orgs[:3]:
            OrganizationStripeSubscriptionFactory.create(organization=organization)

        db_request.user = pretend.stub()
        db_request.has_permission = pretend.call_recorder(lambda perm: False)

        assert views.dashboard(db_request) == {
            "malware_reports_count": None,
            "organizations_count": {"Total": 18, "Community": 11, "Company": 7},
            "organization_applications_count": {"Total": 8, "submitted": 8},
            "active_company_organizations": 3,
            "active_company_organization_users": 6,
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
        }
        assert db_request.has_permission.calls == [
            pretend.call(views.Permissions.AdminObservationsRead),
        ]
