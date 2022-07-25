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

from pyramid.httpexceptions import HTTPBadRequest, HTTPNoContent
from pyramid.view import view_config

from warehouse.subscriptions.interfaces import (
    IGenericBillingService,
    ISubscriptionService,
)
from warehouse.subscriptions.models import SubscriptionStatus


def handle_billing_webhook_event(request, event):
    subscription_service = request.find_service(ISubscriptionService, context=None)

    match event["type"]:
        case "checkout.session.completed":
            session = event["data"]["object"]
            status = session["status"]
            customer_id = session["customer"]
            subscription_id = session["subscription"]
            if session["status"] != "complete":
                raise HTTPBadRequest("Invalid checkout session status")
            if not customer_id:
                raise HTTPBadRequest("Invalid customer ID")
            if not subscription_id:
                raise HTTPBadRequest("Invalid subscription ID")
            if id := subscription_service.find_subscriptionid(subscription_id):
                subscription_service.update_subscription_status(
                    id, SubscriptionStatus.Active
                )
            else:
                # TODO: Activate subscription for customer.
                subscription_service.add_subscription(
                    customer_id,
                    subscription_id,
                    subscription_price_id=None,
                )


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

    return HTTPNoContent
