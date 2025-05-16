# SPDX-License-Identifier: Apache-2.0

import stripe

from pyramid.httpexceptions import HTTPBadRequest, HTTPNoContent
from pyramid.view import view_config

from warehouse.subscriptions.interfaces import IBillingService, ISubscriptionService
from warehouse.subscriptions.models import StripeSubscriptionStatus


def handle_billing_webhook_event(request, event):
    billing_service = request.find_service(IBillingService, context=None)
    subscription_service = request.find_service(ISubscriptionService, context=None)

    match event["type"]:
        # Occurs when a Checkout Session has been successfully completed.
        case "checkout.session.completed":
            checkout_session = event["data"]["object"]
            if not (
                checkout_session["metadata"].get("billing_service") == "pypi"
                and checkout_session["metadata"].get("domain") == billing_service.domain
            ):
                return
            # Get expanded checkout session object
            checkout_session = billing_service.get_checkout_session(
                checkout_session["id"],
                # Provide mock_checkout_session used by MockStripeBillingService only.
                mock_checkout_session=checkout_session,
            )
            status = checkout_session["status"]
            customer_id = checkout_session["customer"]["id"]
            billing_email = checkout_session["customer"]["email"]
            subscription_id = checkout_session["subscription"]["id"]
            if status != "complete":
                raise HTTPBadRequest(f"Invalid checkout session status '{status}'")
            if not customer_id:
                raise HTTPBadRequest("Invalid customer ID")
            if not subscription_id:
                raise HTTPBadRequest("Invalid subscription ID")
            if id := subscription_service.find_subscriptionid(subscription_id):
                # Set subscription status to active.
                subscription_service.update_subscription_status(
                    id, StripeSubscriptionStatus.Active
                )
            else:
                # Get expanded subscription object
                subscription_items = checkout_session["subscription"]["items"]["data"]
                # Activate subscription for customer.
                for subscription_item in subscription_items:
                    subscription_service.add_subscription(
                        customer_id,
                        subscription_id,
                        subscription_item["id"],
                        billing_email,
                    )
        # Occurs whenever a customer’s subscription ends.
        case "customer.subscription.deleted":
            subscription = event["data"]["object"]
            status = subscription["status"]
            customer_id = subscription["customer"]
            subscription_id = subscription["id"]
            if not status or not StripeSubscriptionStatus.has_value(status):
                raise HTTPBadRequest(f"Invalid subscription status '{status}'")
            if not customer_id:
                raise HTTPBadRequest("Invalid customer ID")
            if not subscription_id:
                raise HTTPBadRequest("Invalid subscription ID")
            if id := subscription_service.find_subscriptionid(subscription_id):
                # Set subscription status to canceled.
                subscription_service.update_subscription_status(
                    id, StripeSubscriptionStatus.Canceled
                )
        # Occurs whenever a subscription changes e.g. status changes.
        case "customer.subscription.updated":
            subscription = event["data"]["object"]
            status = subscription["status"]
            customer_id = subscription["customer"]
            subscription_id = subscription["id"]
            if not status or not StripeSubscriptionStatus.has_value(status):
                raise HTTPBadRequest(f"Invalid subscription status '{status}'")
            if not customer_id:
                raise HTTPBadRequest("Invalid customer ID")
            if not subscription_id:
                raise HTTPBadRequest("Invalid subscription ID")

            if id := subscription_service.find_subscriptionid(subscription_id):
                # Update subscription status.
                subscription_service.update_subscription_status(id, status)
        # Occurs whenever a customer is deleted.
        case "customer.deleted":
            customer = event["data"]["object"]
            customer_id = customer["id"]
            if not customer_id:
                raise HTTPBadRequest("Invalid customer ID")
            if subscription_service.get_subscriptions_by_customer(customer_id):
                # Delete the customer and all associated subscription data
                subscription_service.delete_customer(customer_id)
        # Occurs whenever a customer is updated.
        case "customer.updated":
            customer = event["data"]["object"]
            customer_id = customer["id"]
            billing_email = customer["email"]
            if not customer_id:
                raise HTTPBadRequest("Invalid customer ID")
            if not billing_email:
                raise HTTPBadRequest("Invalid billing email")
            # Update customer email
            subscription_service.update_customer_email(customer_id, billing_email)


@view_config(
    route_name="api.billing.webhook",
    require_csrf=False,
    require_methods=["POST"],
    uses_session=True,
)
def billing_webhook(request):
    billing_service = request.find_service(IBillingService, context=None)

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
