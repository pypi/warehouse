# SPDX-License-Identifier: Apache-2.0

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

    def get_customer(subscription_id):
        """
        Fetch the Customer resource attached to the Subscription
        """

    def create_customer(name, description):
        """
        Create the Customer resource via Billing API with the given name and description
        """

    def update_customer(customer_id, name, description):
        """
        Update a Customer resource via Billing API with the given name and description
        """

    def create_checkout_session(customer_id, price_ids, success_url, cancel_url):
        """
        # Create new Checkout Session for the order
        # For full details see https://stripe.com/docs/api/checkout/sessions/create
        """

    def create_portal_session(customer_id, return_url):
        """
        Return customer portal session to allow customer to managing their subscription
        """

    def webhook_received(payload, sig_header):
        """
        Return parsed webhook event from Stripe
        """

    def create_or_update_product(name, description, tax_code, unit_label):
        """
        Create product resource via Billing API, or update an active
        product resource with the same name
        """

    def create_product(name, description, tax_code, unit_label):
        """
        Create and return a product resource via Billing API
        """

    def retrieve_product(product_id):
        """
        Get a product resource by id via Billing API
        """

    def update_product(product_id, name, description, tax_code, unit_label):
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

    def sync_product(subscription_product):
        """
        Synchronize a product resource via Billing API with a
        subscription product from the database.
        """

    def create_or_update_price(unit_amount, currency, product_id, tax_behavior):
        """
        Create price resource via Billing API, or update an active price
        resource with the same product and currency
        """

    def create_price(unit_amount, currency, product_id, tax_behavior):
        """
        Create and return a price resource via Billing API
        """

    def retrieve_price(price_id):
        """
        Get a price resource via Billing API
        """

    def update_price(price_id, **parameters):
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

    def sync_price(subscription_price):
        """
        Synchronize a price resource via Billing API with a
        subscription price from the database.
        """

    def cancel_subscription(subscription_id):
        """
        Cancels a customer’s subscription immediately.
        The customer will not be charged again for the subscription.
        """

    def create_or_update_usage_record(subscription_item_id, organization_member_count):
        """
        Creates a usage record via Billing API
        for a specified subscription item and date with default=now,
        and fills it with a quantity=number of members in the org.
        """


class IBillingService(IGenericBillingService):
    pass


class ISubscriptionService(Interface):
    def get_subscription(id):
        """
        Get a subscription by id
        """

    def find_subscriptionid(subscription_id):
        """
        Find the unique subscription identifier for the subscription,
        by the payment service provider subscription id or None
        """

    def add_subscription(
        customer_id, subscription_id, subscription_item_id, billing_email
    ):
        """
        Attempts to create a subscription object for the organization
        with the specified customer ID and subscription ID
        """

    def update_subscription_status(id, status):
        """
        Update the status of a subscription object by subscription.id
        """

    def delete_subscription(id):
        """
        Delete a subscription by ID
        """

    def get_subscriptions_by_customer(customer_id):
        """
        Get a list of subscriptions tied to the given customer ID
        """

    def get_stripe_customer(stripe_customer_id):
        """
        Get a stripe customer by id
        """

    def find_stripe_customer_id(customer_id):
        """
        Get the stripe customer UUID tied to the given customer ID
        """

    def delete_customer(customer_id):
        """
        Deletes a customer and all associated subscription data
        """

    def add_stripe_customer(customer_id):
        """
        Create a StripeCustomer object to associate to the Stripe customer ID
        """

    def update_customer_email(customer_id, billing_email):
        """
        Update the customer's billing email
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

    def get_or_create_default_subscription_price():
        """
        Get the default subscription price or initialize one if nothing is found
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
