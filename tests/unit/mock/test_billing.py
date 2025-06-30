# SPDX-License-Identifier: Apache-2.0

import pytest

from pyramid.httpexceptions import HTTPNotFound, HTTPSeeOther

from warehouse.mock import billing

from ...common.db.organizations import OrganizationFactory


class TestMockBillingViews:
    @pytest.fixture
    def organization(self):
        return OrganizationFactory.create()

    def test_disable_organizations(self, db_request, organization):
        db_request.organization_access = False
        with pytest.raises(HTTPNotFound):
            billing.MockBillingViews(organization, db_request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_mock_checkout_session(self, db_request, organization):
        view = billing.MockBillingViews(organization, db_request)
        result = view.mock_checkout_session()

        assert result == {"organization": organization}

    @pytest.mark.usefixtures("_enable_organizations")
    def test_mock_portal_session(self, db_request, organization):
        view = billing.MockBillingViews(organization, db_request)
        result = view.mock_portal_session()

        assert result == {"organization": organization}

    @pytest.mark.usefixtures("_enable_organizations")
    def test_mock_trigger_checkout_session_completed(
        self, db_request, organization, monkeypatch
    ):
        monkeypatch.setattr(
            db_request,
            "route_path",
            lambda *a, **kw: "/manage/organizations/",
        )
        monkeypatch.setattr(
            billing,
            "handle_billing_webhook_event",
            lambda *a, **kw: None,
        )

        view = billing.MockBillingViews(organization, db_request)
        result = view.mock_trigger_checkout_session_completed()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organizations/"
