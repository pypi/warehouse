# SPDX-License-Identifier: Apache-2.0

import pytest

from pyramid.httpexceptions import HTTPNotFound, HTTPSeeOther

from warehouse.mock import billing
from warehouse.subscriptions.interfaces import IBillingService
from warehouse.subscriptions.services import StripeBillingService

from ...common.db.organizations import (
    OrganizationFactory,
    OrganizationStripeCustomerFactory,
)


class TestMockBillingViews:
    @pytest.fixture
    def organization(self):
        return OrganizationFactory.create()

    def test_not_mock_billing_service_raises_404(
        self, mocker, db_request, pyramid_services, organization
    ):
        pyramid_services.register_service(
            mocker.create_autospec(StripeBillingService, instance=True),
            IBillingService,
            None,
            name="",
        )

        with pytest.raises(HTTPNotFound):
            billing.MockBillingViews(organization, db_request)

    def test_mock_checkout_session(self, db_request, organization):
        view = billing.MockBillingViews(organization, db_request)
        result = view.mock_checkout_session()

        assert result == {"organization": organization}

    def test_mock_portal_session(self, db_request, organization):
        view = billing.MockBillingViews(organization, db_request)
        result = view.mock_portal_session()

        assert result == {"organization": organization}

    def test_mock_trigger_checkout_session_completed(
        self, db_request, organization, mocker
    ):
        route_path = mocker.patch.object(
            db_request,
            "route_path",
            autospec=True,
            return_value="/manage/organizations/",
        )
        handle_billing_webhook_event = mocker.patch.object(
            billing, "handle_billing_webhook_event", autospec=True
        )

        view = billing.MockBillingViews(organization, db_request)
        result = view.mock_trigger_checkout_session_completed()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organizations/"
        route_path.assert_called_once_with("manage.organizations")
        handle_billing_webhook_event.assert_called_once_with(db_request, mocker.ANY)
        event = handle_billing_webhook_event.call_args.args[1]
        assert event["type"] == "checkout.session.completed"
        session = event["data"]["object"]
        assert session["id"].startswith("mockcs_")
        assert session["subscription"].startswith("mocksub_")
        assert session["customer"] is None
        assert session["customer_email"] is None
        assert session["status"] == "complete"
        assert session["metadata"] == {"billing_service": "pypi", "domain": "localhost"}

    def test_mock_trigger_checkout_session_completed_with_customer(
        self, db_request, organization, mocker
    ):
        stripe_customer = OrganizationStripeCustomerFactory.create(
            organization=organization
        ).customer
        mocker.patch.object(db_request, "route_path", autospec=True)
        handle_billing_webhook_event = mocker.patch.object(
            billing, "handle_billing_webhook_event", autospec=True
        )

        view = billing.MockBillingViews(organization, db_request)
        view.mock_trigger_checkout_session_completed()

        session = handle_billing_webhook_event.call_args.args[1]["data"]["object"]
        assert session["customer"] == stripe_customer.customer_id
        assert session["customer_email"] == stripe_customer.billing_email
