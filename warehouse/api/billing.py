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


import stripe

from pyramid.httpexceptions import HTTPBadRequest, HTTPNoContent, HTTPNotFound
from pyramid.view import view_config

from warehouse.subscriptions.interfaces import (
    IGenericBillingService,
    ISubscriptionService,
)
from warehouse.subscriptions.models import SubscriptionStatus


def handle_billing_webhook_event(request, event):
    subscription_service = request.find_service(ISubscriptionService, context=None)

    match event["type"]:
        # Occurs when a Checkout Session has been successfully completed.
        case "checkout.session.completed":
            checkout_session = event["data"]["object"]
            status = checkout_session["status"]
            customer_id = checkout_session["customer"]
            subscription_id = checkout_session["subscription"]
            if status != "complete":
                raise HTTPBadRequest("Invalid checkout session status")
            if not customer_id:
                raise HTTPBadRequest("Invalid customer ID")
            if not subscription_id:
                raise HTTPBadRequest("Invalid subscription ID")
            if id := subscription_service.find_subscriptionid(subscription_id):
                # Set subscription status to active.
                subscription_service.update_subscription_status(
                    id, SubscriptionStatus.Active
                )
            else:
                # Activate subscription for customer.
                subscription_service.add_subscription(
                    request, customer_id, subscription_id
                )
        # Occurs whenever a customer’s subscription ends.
        case "customer.subscription.deleted":
            subscription = event["data"]["object"]
            status = subscription["status"]
            customer_id = subscription["customer"]
            subscription_id = subscription["id"]
            if not status or not SubscriptionStatus.has_value(status):
                raise HTTPBadRequest("Invalid subscription status")
            if not customer_id:
                raise HTTPBadRequest("Invalid customer ID")
            if not subscription_id:
                raise HTTPBadRequest("Invalid subscription ID")
            if id := subscription_service.find_subscriptionid(subscription_id):
                # Set subscription status to canceled.
                subscription_service.update_subscription_status(
                    id, SubscriptionStatus.Canceled
                )
            else:
                raise HTTPNotFound("Subscription not found")
        # Occurs whenever a subscription changes e.g. status changes.
        case "customer.subscription.updated":
            subscription = event["data"]["object"]
            status = subscription["status"]
            customer_id = subscription["customer"]
            subscription_id = subscription["id"]
            if not status or not SubscriptionStatus.has_value(status):
                raise HTTPBadRequest("Invalid subscription status")
            if not customer_id:
                raise HTTPBadRequest("Invalid customer ID")
            if not subscription_id:
                raise HTTPBadRequest("Invalid subscription ID")

            if id := subscription_service.find_subscriptionid(subscription_id):
                db_subscription = subscription_service.get_subscription(
                    subscription_service.find_subscriptionid(id)
                )
                if db_subscription.status != status:
                    # Update subscription status.
                    subscription_service.update_subscription_status(
                        db_subscription.id, status
                    )
            else:
                raise HTTPNotFound("Subscription not found")
        # Occurs whenever a customer is deleted.
        case "customer.deleted":
            customer = event["data"]["object"]
            customer_id = customer["id"]
            if not customer_id:
                raise HTTPBadRequest("Invalid customer ID")
            if subscription_service.get_subscriptions_by_customer(customer_id):
                # Delete the customer and all associated subscription data
                subscription_service.delete_customer(customer_id)
            else:
                raise HTTPNotFound("Customer subscription data not found")


@view_config(
    route_name="api.billing.webhook",
    require_csrf=False,
    require_methods=["POST"],
    uses_session=True,
)
def billing_webhook(request):
    billing_service = request.find_service(IGenericBillingService, context=None)

    try:
        payload = request.body
        sig_header = request.headers.get("Stripe-Signature")
        event = billing_service.webhook_received(payload, sig_header)
    except ValueError:
        raise HTTPBadRequest("Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPBadRequest("Invalid signature")

    handle_billing_webhook_event(request, event)

    return HTTPNoContent()
