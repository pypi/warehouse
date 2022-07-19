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

from zope.interface import Interface


class IGenericBillingService(Interface):
    def create_service(context, request):
        """
        Create appropriate billing service based on environment
        """

    def get_checkout_session(session_id):
        """
        Fetch the Checkout Session to based on the session_id passed to the success page
        """

    # def get_customer(subscription_id):
    #     """
    #     Fetch the Customer resource attached to the Subscription
    #     """

    def create_checkout_session(product_id, success_url, cancel_url):
        """
        # Create new Checkout Session for the order
        # For full details see https://stripe.com/docs/api/checkout/sessions/create
        """

    def create_portal_session(organization_id, return_url):
        """
        Return customer portal session to allow customer to managing their subscription
        """

    def webhook_received(request):
        """
        Webhooks to handle stripe events
        """

    def create_product(name, description, tax_code):
        """
        Create and return a product resource via Billing API
        """

    def retrieve_product(product_id):
        """
        Get a product resource by id via Billing API
        """

    def update_product(product_id, name, description, tax_code):
        """
        Update a product resource via Billing API
        only allowing update of those attributes we use
        return the updated product
        """

    def list_all_products(limit=10):
        """
        Get list of all price resources via Billing API
        Limit can range between 1 and 100, default is 10
        """

    def delete_product(product_id):
        """
        Delete a product resource via Billing API
        """

    def search_products(query, limit=10):
        """
        Search for product resources via Billing API
        example: query="active:'true'"
        """

    def create_price(unit_amount, currency, recurring, product_id, tax_behavior):
        """
        Create and return a price resource via Billing API
        """

    def retrieve_price(price_id):
        """
        Get a price resource via Billing API
        """

    def update_price(price_id, active, tax_behavior):
        """
        Update a price resource by id via Billing API
        only allowing update of those attributes we use
        return the updated price
        """

    def list_all_prices(limit=10):
        """
        Get list of all price resources via Billing API
        Limit can range between 1 and 100, default is 10
        """

    def search_prices(query, limit=10):
        """
        Search for price resources via Billing API
        example: query="active:'true'"
        """


class IBillingService(IGenericBillingService):
    pass


class ISubscriptionService(Interface):
    def get_publishable_key(request):
        """
        Fetch the publishable key from the billing api
        """

    def get_subscription(id):
        """
        Get a subscription by id
        """

    def find_subscriptionid(subscription_id):
        """
        Find the unique subscription identifier for the subscription,
        by the payment service provider subscription id or None
        """

    def add_subscription(customer_id, subscription_id, price_id):
        """
        Attempts to create a subscription object with the specified
        customer id, subscription id and price id
        """

    def update_subscription_status(id, status):
        """
        Update the status of a subscription object by subscription.id
        """

    def get_subscription_product(subscription_product_id):
        """
        Get a product by subscription product id
        """

    def get_subscription_products():
        """
        Get a list of all subscription products
        """

    def find_subscription_productid(search_term):
        """
        Find the unique product identifier for the product name,
        product id or None if nothing is found
        """

    def add_subscription_product(product_name, description, product_id, tax_code):
        """
        Add a subscription product
        """

    def update_subscription_product(subscription_product_id, **changes):
        """
        Accepts a subscription product object
        and attempts an update with those attributes
        """

    def delete_subscription_product(subscription_product_id):
        """
        Delete a subscription product
        """

    def get_subscription_price(subscription_price_id):
        """
        Get a subscription price by id
        """

    def get_subscription_prices():
        """
        Get a list of all subscription prices
        """

    def find_subscription_priceid(search_term):
        """
        Find the unique price identifier for the price id, product id,
        subscription product id or None if nothing is found
        """

    def add_subscription_price(
        price_id,
        currency,
        subscription_product_id,
        unit_amount,
        recurring,
        tax_behavior,
    ):
        """
        Add a subscription price
        """

    def update_subscription_price(subscription_price_id, **changes):
        """
        Accepts a subscription price object
        and attempts an update with those attributes
        """

    def delete_subscription_price(subscription_price_id):
        """
        Delete a subscription price
        """
