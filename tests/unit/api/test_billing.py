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

import random
import time

from string import ascii_letters, digits

import pretend
import pytest
import stripe

from pyramid.httpexceptions import HTTPBadRequest, HTTPNoContent, HTTPNotFound
from webob.multidict import MultiDict

from warehouse.api.billing import billing_webhook, handle_billing_webhook_event

from ...common.db.organizations import (
    OrganizationFactory,
    OrganizationSubscriptionFactory,
)
from ...common.db.subscriptions import SubscriptionFactory


class TestBillingWebhook:
    # checkout.session.completed
    def test_handle_billing_webhook_event_checkout_complete_update(
        self, db_request, subscription_service
    ):
        organization = OrganizationFactory.create(customer_id="cus_123")
        subscription = SubscriptionFactory.create(customer_id=organization.customer_id)
        OrganizationSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )

        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": organization.customer_id,
                    "status": "complete",
                    "subscription": subscription.subscription_id,
                },
            },
        }

        handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_checkout_complete_add(
        self, db_request, subscription_service
    ):
        organization = OrganizationFactory.create(customer_id="cus_123")

        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": organization.customer_id,
                    "status": "complete",
                    "subscription": "sub_12345",
                },
            },
        }

        handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_checkout_complete_invalid_status(
        self, db_request
    ):
        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": "cus_1234",
                    "status": "invalid_status",
                    "subscription": "sub_12345",
                },
            },
        }

        with pytest.raises(HTTPBadRequest):
            handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_checkout_complete_invalid_customer(
        self, db_request
    ):
        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": "",
                    "status": "complete",
                    "subscription": "sub_12345",
                },
            },
        }

        with pytest.raises(HTTPBadRequest):
            handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_checkout_complete_invalid_subscription(
        self, db_request
    ):
        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": "cus_1234",
                    "status": "complete",
                    "subscription": "",
                },
            },
        }

        with pytest.raises(HTTPBadRequest):
            handle_billing_webhook_event(db_request, event)

    # customer.subscription.deleted
    def test_handle_billing_webhook_event_subscription_deleted_update(
        self, db_request, subscription_service
    ):
        organization = OrganizationFactory.create(customer_id="cus_123")
        subscription = SubscriptionFactory.create(customer_id=organization.customer_id)
        OrganizationSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )

        event = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "customer": organization.customer_id,
                    "status": "canceled",
                    "id": subscription.subscription_id,
                },
            },
        }

        handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_subscription_deleted_not_found(
        self, db_request, subscription_service
    ):
        organization = OrganizationFactory.create(customer_id="cus_123")

        event = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "customer": organization.customer_id,
                    "status": "canceled",
                    "id": "sub_12345",
                },
            },
        }

        with pytest.raises(HTTPNotFound):
            handle_billing_webhook_event(db_request, event)

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
            handle_billing_webhook_event(db_request, event)

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
            handle_billing_webhook_event(db_request, event)

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
            handle_billing_webhook_event(db_request, event)

    # customer.subscription.updated
    def test_handle_billing_webhook_event_subscription_updated_update(
        self, db_request, subscription_service
    ):
        organization = OrganizationFactory.create(customer_id="cus_123")
        subscription = SubscriptionFactory.create(customer_id=organization.customer_id)
        OrganizationSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )

        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": organization.customer_id,
                    "status": "canceled",
                    "id": subscription.subscription_id,
                },
            },
        }

        handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_subscription_updated_not_found(
        self, db_request, subscription_service
    ):
        organization = OrganizationFactory.create(customer_id="cus_123")

        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": organization.customer_id,
                    "status": "canceled",
                    "id": "sub_12345",
                },
            },
        }

        with pytest.raises(HTTPNotFound):
            handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_subscription_updated_no_change(
        self, db_request
    ):
        organization = OrganizationFactory.create(customer_id="cus_123")
        subscription = SubscriptionFactory.create(
            customer_id=organization.customer_id, status="active"
        )
        OrganizationSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )

        assert subscription.status == "active"

        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": organization.customer_id,
                    "status": "active",
                    "id": subscription.subscription_id,
                },
            },
        }

        handle_billing_webhook_event(db_request, event)

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
            handle_billing_webhook_event(db_request, event)

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
            handle_billing_webhook_event(db_request, event)

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
            handle_billing_webhook_event(db_request, event)

    # customer.deleted
    def test_handle_billing_webhook_event_customer_deleted(
        self, db_request, subscription_service
    ):
        organization = OrganizationFactory.create(customer_id="cus_123")
        subscription = SubscriptionFactory.create(customer_id=organization.customer_id)
        OrganizationSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )

        event = {
            "type": "customer.deleted",
            "data": {
                "object": {
                    "id": organization.customer_id,
                },
            },
        }

        handle_billing_webhook_event(db_request, event)

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

        with pytest.raises(HTTPNotFound):
            handle_billing_webhook_event(db_request, event)

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
            handle_billing_webhook_event(db_request, event)

    def test_handle_billing_webhook_event_unmatched_event(self, db_request):
        event = {
            "type": "your.birthday",
            "data": {
                "object": {
                    "id": "day_1234",
                },
            },
        }

        handle_billing_webhook_event(db_request, event)
