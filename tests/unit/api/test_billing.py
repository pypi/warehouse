# SPDX-License-Identifier: Apache-2.0

import json

import pretend
import pytest
import stripe

from pyramid.httpexceptions import HTTPBadRequest, HTTPNoContent

from warehouse.api import billing

from ...common.db.organizations import (
    OrganizationFactory,
    OrganizationStripeCustomerFactory,
    OrganizationStripeSubscriptionFactory,
)
from ...common.db.subscriptions import StripeCustomerFactory, StripeSubscriptionFactory


class TestHandleBillingWebhookEvent:
    # checkout.session.completed
    def test_handle_billing_webhook_event_checkout_complete_not_us(
        self, db_request, subscription_service, monkeypatch, billing_service
    ):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = StripeSubscriptionFactory.create(customer=stripe_customer)
        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )

        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_12345",
                    "customer": stripe_customer.customer_id,
                    "status": "complete",
                    "subscription": subscription.subscription_id,
                    # Missing expected metadata tags (billing_service, domain)
                    "metadata": {},
                },
            },
        }

        checkout_session = {
            "id": "cs_test_12345",
            "customer": {
                "id": stripe_customer.customer_id,
                "email": "good@day.com",
            },
            "status": "complete",
            "subscription": {
                "id": subscription.subscription_id,
                "items": {
                    "data": [{"id": "si_12345"}],
                },
            },
        }

        get_checkout_session = pretend.call_recorder(lambda *a, **kw: checkout_session)
        monkeypatch.setattr(
            billing_service, "get_checkout_session", get_checkout_session
        )

        billing.handle_billing_webhook_event(db_request, event)

        assert (
            get_checkout_session.calls == []
        )  # Should have stopped immediately before this call

    def test_handle_billing_webhook_event_checkout_complete_update(
        self, db_request, subscription_service, monkeypatch, billing_service
    ):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = StripeSubscriptionFactory.create(customer=stripe_customer)
        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )

        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_12345",
                    "customer": stripe_customer.customer_id,
                    "status": "complete",
                    "subscription": subscription.subscription_id,
                    "metadata": {
                        "billing_service": "pypi",
                        "domain": "localhost",
                    },
                },
            },
        }

        checkout_session = {
            "id": "cs_test_12345",
            "customer": {
                "id": stripe_customer.customer_id,
                "email": "good@day.com",
            },
            "status": "complete",
            "subscription": {
                "id": subscription.subscription_id,
                "items": {
                    "data": [{"id": "si_12345"}],
                },
            },
        }

        get_checkout_session = pretend.call_recorder(lambda *a, **kw: checkout_session)
        monkeypatch.setattr(
            billing_service, "get_checkout_session", get_checkout_session
        )

        billing.handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_checkout_complete_add(
        self, db_request, subscription_service, monkeypatch, billing_service
    ):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )

        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_12345",
                    "customer": stripe_customer.customer_id,
                    "status": "complete",
                    "subscription": "sub_12345",
                    "metadata": {
                        "billing_service": "pypi",
                        "domain": "localhost",
                    },
                },
            },
        }

        checkout_session = {
            "id": "cs_test_12345",
            "customer": {
                "id": stripe_customer.customer_id,
                "email": "good@day.com",
            },
            "status": "complete",
            "subscription": {
                "id": "sub_12345",
                "items": {
                    "data": [{"id": "si_12345"}],
                },
            },
        }

        get_checkout_session = pretend.call_recorder(lambda *a, **kw: checkout_session)
        monkeypatch.setattr(
            billing_service, "get_checkout_session", get_checkout_session
        )

        billing.handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_checkout_complete_invalid_status(
        self, db_request
    ):
        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_12345",
                    "customer": "cus_1234",
                    "status": "invalid_status",
                    "subscription": "sub_12345",
                    "metadata": {
                        "billing_service": "pypi",
                        "domain": "localhost",
                    },
                },
            },
        }

        with pytest.raises(HTTPBadRequest):
            billing.handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_checkout_complete_invalid_customer(
        self, db_request, monkeypatch, billing_service
    ):
        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_12345",
                    "customer": "",
                    "status": "complete",
                    "subscription": "sub_12345",
                    "metadata": {
                        "billing_service": "pypi",
                        "domain": "localhost",
                    },
                },
            },
        }

        checkout_session = {
            "id": "cs_test_12345",
            "customer": {
                "id": "",
                "email": "good@day.com",
            },
            "status": "complete",
            "subscription": {
                "id": "sub_12345",
                "items": {
                    "data": [{"id": "si_12345"}],
                },
            },
        }

        get_checkout_session = pretend.call_recorder(lambda *a, **kw: checkout_session)
        monkeypatch.setattr(
            billing_service, "get_checkout_session", get_checkout_session
        )

        with pytest.raises(HTTPBadRequest):
            billing.handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_checkout_complete_invalid_subscription(
        self, db_request, monkeypatch, billing_service
    ):
        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_12345",
                    "customer": "cus_1234",
                    "status": "complete",
                    "subscription": "",
                    "metadata": {
                        "billing_service": "pypi",
                        "domain": "localhost",
                    },
                },
            },
        }

        checkout_session = {
            "id": "cs_test_12345",
            "customer": {
                "id": "cus_1234",
                "email": "good@day.com",
            },
            "status": "complete",
            "subscription": {
                "id": "",
            },
        }

        get_checkout_session = pretend.call_recorder(lambda *a, **kw: checkout_session)
        monkeypatch.setattr(
            billing_service, "get_checkout_session", get_checkout_session
        )

        with pytest.raises(HTTPBadRequest):
            billing.handle_billing_webhook_event(db_request, event)

    # customer.subscription.deleted
    def test_handle_billing_webhook_event_subscription_deleted_update(
        self, db_request, subscription_service
    ):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = StripeSubscriptionFactory.create(customer=stripe_customer)
        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )

        event = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "customer": stripe_customer.customer_id,
                    "status": "canceled",
                    "id": subscription.subscription_id,
                },
            },
        }

        billing.handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_subscription_deleted(
        self, db_request, subscription_service
    ):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )

        event = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "customer": stripe_customer.customer_id,
                    "status": "canceled",
                    "id": "sub_12345",
                },
            },
        }

        billing.handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_subscription_deleted_invalid_status(
        self, db_request
    ):
        event = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "customer": "cus_1234",
                    "status": "invalid_status",
                    "id": "sub_12345",
                },
            },
        }

        with pytest.raises(HTTPBadRequest):
            billing.handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_subscription_deleted_invalid_customer(
        self, db_request
    ):
        event = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "customer": "",
                    "status": "canceled",
                    "id": "sub_12345",
                },
            },
        }

        with pytest.raises(HTTPBadRequest):
            billing.handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_subscription_deleted_invalid_subscription(
        self, db_request
    ):
        event = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "customer": "cus_1234",
                    "status": "canceled",
                    "id": "",
                },
            },
        }

        with pytest.raises(HTTPBadRequest):
            billing.handle_billing_webhook_event(db_request, event)

    # customer.subscription.updated
    def test_handle_billing_webhook_event_subscription_updated_update(
        self, db_request, subscription_service
    ):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = StripeSubscriptionFactory.create(customer=stripe_customer)
        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )

        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": stripe_customer.customer_id,
                    "status": "canceled",
                    "id": subscription.subscription_id,
                },
            },
        }

        billing.handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_subscription_updated_not_found(
        self, db_request, subscription_service
    ):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )

        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": stripe_customer.customer_id,
                    "status": "canceled",
                    "id": "sub_12345",
                },
            },
        }

        billing.handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_subscription_updated_no_change(
        self, db_request
    ):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = StripeSubscriptionFactory.create(customer=stripe_customer)
        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )

        assert subscription.status == "active"

        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": stripe_customer.customer_id,
                    "status": "active",
                    "id": subscription.subscription_id,
                },
            },
        }

        billing.handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_subscription_updated_invalid_status(
        self, db_request
    ):
        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": "cus_1234",
                    "status": "invalid_status",
                    "id": "sub_12345",
                },
            },
        }

        with pytest.raises(HTTPBadRequest):
            billing.handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_subscription_updated_invalid_customer(
        self, db_request
    ):
        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": "",
                    "status": "canceled",
                    "id": "sub_12345",
                },
            },
        }

        with pytest.raises(HTTPBadRequest):
            billing.handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_subscription_updated_invalid_subscription(
        self, db_request
    ):
        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": "cus_1234",
                    "status": "canceled",
                    "id": "",
                },
            },
        }

        with pytest.raises(HTTPBadRequest):
            billing.handle_billing_webhook_event(db_request, event)

    # customer.deleted
    def test_handle_billing_webhook_event_customer_deleted(
        self, db_request, subscription_service
    ):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = StripeSubscriptionFactory.create(customer=stripe_customer)
        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )

        event = {
            "type": "customer.deleted",
            "data": {
                "object": {
                    "id": stripe_customer.customer_id,
                },
            },
        }

        billing.handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_customer_deleted_no_subscriptions(
        self, db_request
    ):
        event = {
            "type": "customer.deleted",
            "data": {
                "object": {
                    "id": "cus_12345",
                },
            },
        }

        billing.handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_customer_deleted_invalid_customer(
        self, db_request
    ):
        event = {
            "type": "customer.deleted",
            "data": {
                "object": {
                    "id": "",
                },
            },
        }

        with pytest.raises(HTTPBadRequest):
            billing.handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_unmatched_event(self, db_request):
        event = {
            "type": "your.birthday",
            "data": {
                "object": {
                    "id": "day_1234",
                },
            },
        }

        billing.handle_billing_webhook_event(db_request, event)

    # customer.updated
    def test_handle_billing_webhook_event_customer_updated_email(self, db_request):
        event = {
            "type": "customer.updated",
            "data": {
                "object": {
                    "id": "cus_12345",
                    "email": "great@day.com",
                },
            },
        }

        billing.handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_customer_updated_invalid_customer(
        self, db_request
    ):
        event = {
            "type": "customer.updated",
            "data": {
                "object": {
                    "id": "",
                    "email": "good@day.com",
                },
            },
        }

        with pytest.raises(HTTPBadRequest):
            billing.handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_no_billing_email(self, db_request):
        event = {
            "type": "customer.updated",
            "data": {
                "object": {
                    "id": "cus_12345",
                    "email": "",
                },
            },
        }

        with pytest.raises(HTTPBadRequest):
            billing.handle_billing_webhook_event(db_request, event)


class TestBillingWebhook:
    def test_billing_webhook(self, pyramid_request, billing_service, monkeypatch):
        pyramid_request.body = json.dumps({"type": "mock.webhook.payload"})
        pyramid_request.headers = {"Stripe-Signature": "mock-stripe-signature"}

        monkeypatch.setattr(
            billing_service,
            "webhook_received",
            lambda p, s: json.loads(p),
        )

        monkeypatch.setattr(
            billing, "handle_billing_webhook_event", lambda *a, **kw: None
        )

        result = billing.billing_webhook(pyramid_request)

        assert isinstance(result, HTTPNoContent)

    def test_billing_webhook_value_error(
        self, pyramid_request, billing_service, monkeypatch
    ):
        pyramid_request.body = json.dumps({"type": "mock.webhook.payload"})
        pyramid_request.headers = {"Stripe-Signature": "mock-stripe-signature"}

        def webhook_received(payload, sig_header):
            raise ValueError()

        monkeypatch.setattr(billing_service, "webhook_received", webhook_received)

        with pytest.raises(HTTPBadRequest):
            billing.billing_webhook(pyramid_request)

    def test_billing_webhook_signature_error(
        self, pyramid_request, billing_service, monkeypatch
    ):
        pyramid_request.body = json.dumps({"type": "mock.webhook.payload"})
        pyramid_request.headers = {"Stripe-Signature": "mock-stripe-signature"}

        def webhook_received(payload, sig_header):
            raise stripe.error.SignatureVerificationError("signature error", sig_header)

        monkeypatch.setattr(billing_service, "webhook_received", webhook_received)

        with pytest.raises(HTTPBadRequest):
            billing.billing_webhook(pyramid_request)
