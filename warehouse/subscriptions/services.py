# SPDX-License-Identifier: Apache-2.0

import random

from string import ascii_letters, digits

import stripe

from sqlalchemy import or_
from sqlalchemy.exc import NoResultFound
from zope.interface import implementer

from warehouse.organizations.models import (
    OrganizationStripeCustomer,
    OrganizationStripeSubscription,
)
from warehouse.subscriptions.interfaces import IBillingService, ISubscriptionService
from warehouse.subscriptions.models import (
    StripeCustomer,
    StripeSubscription,
    StripeSubscriptionItem,
    StripeSubscriptionPrice,
    StripeSubscriptionPriceInterval,
    StripeSubscriptionProduct,
    StripeSubscriptionStatus,
)


class GenericBillingService:
    def __init__(self, api, publishable_key, webhook_secret, domain):
        self.api = api
        self.publishable_key = publishable_key
        self.webhook_secret = webhook_secret
        self.domain = domain

    @classmethod
    def create_service(cls, context, request):
        """
        Create appropriate billing service based on environment
        """
        raise NotImplementedError

    def get_checkout_session(self, session_id, **kwargs):
        """
        Fetch the Checkout Session to based on the session_id passed to the success page
        """
        checkout_session = self.api.checkout.Session.retrieve(
            session_id,
            expand=["customer", "line_items", "subscription"],
        )
        return checkout_session

    def get_customer(self, subscription_id):
        """
        Fetch the Customer resource attached to the Subscription
        """
        subscription = self.api.Subscription.retrieve(
            subscription_id,
            expand=["customer"],
        )
        return subscription.customer

    def create_customer(self, name, description):
        """
        Create the Customer resource via Billing API with the given name and description
        """
        return self.api.Customer.create(
            name=name,
            description=description[:300],
            metadata={"billing_service": "pypi", "domain": self.domain},
        )

    def update_customer(self, customer_id, name, description):
        return self.api.Customer.modify(
            customer_id,
            name=name,
            description=description[:300],
        )

    def create_checkout_session(self, customer_id, price_ids, success_url, cancel_url):
        """
        # Create new Checkout Session for the order
        # For full details see https://stripe.com/docs/api/checkout/sessions/create
        """
        checkout_session = self.api.checkout.Session.create(
            customer=customer_id,
            success_url=success_url,
            cancel_url=cancel_url,
            mode="subscription",
            line_items=[{"price": price_id} for price_id in price_ids],
            metadata={"billing_service": "pypi", "domain": self.domain},
            # Uncomment `automatic_tax` to calculate tax automatically.
            # Requires active tax settings on Stripe Dashboard.
            # https://dashboard.stripe.com/settings/tax/activate
            # automatic_tax={"enabled": True},
        )
        return checkout_session

    def create_portal_session(self, customer_id, return_url):
        """
        Return customer portal session to allow customer to managing their subscription
        """
        portal_session = self.api.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return portal_session

    # See Stripe webhook documentation:
    # https://stripe.com/docs/api/webhook_endpoints/create#create_webhook_endpoint-enabled_events
    # https://stripe.com/docs/webhooks/quickstart
    def webhook_received(self, payload, sig_header):
        """
        Return parsed webhook event from Stripe
        """
        return stripe.Webhook.construct_event(payload, sig_header, self.webhook_secret)

    def create_or_update_product(self, name, description, tax_code, unit_label):
        """
        Create product resource via Billing API, or update an active
        product resource with the same name
        """
        # Search for active product with the given name.
        # (a) Search exact or substring match for name as supported by Stripe API.
        #     https://stripe.com/docs/search#query-fields-for-products
        product_search = self.search_products(f'active:"true" name:"{name}"')
        # (b) Make sure name is an exact match.
        products = [
            product for product in product_search["data"] if product["name"] == name
        ]
        if products:
            product = max(products, key=lambda p: p["created"])
            return self.update_product(
                product["id"], name, description, tax_code, unit_label
            )
        else:
            return self.create_product(name, description, tax_code, unit_label)

    def create_product(self, name, description, tax_code, unit_label):
        """
        Create and return a product resource via Billing API
        """
        return self.api.Product.create(
            name=name,
            description=description,
            tax_code=tax_code,
            unit_label=unit_label,
            metadata={"billing_service": "pypi", "domain": self.domain},
        )

    def retrieve_product(self, product_id):
        """
        Get a product resource by id via Billing API
        """
        return self.api.Product.retrieve(product_id)

    def update_product(self, product_id, name, description, tax_code, unit_label):
        """
        Update a product resource via Billing API
        only allowing update of those attributes we use
        return the updated product
        """
        return self.api.Product.modify(
            product_id,
            name=name,
            description=description,
            tax_code=tax_code,
            unit_label=unit_label,
        )

    def list_all_products(self, limit=10):
        """
        Get list of all price resources via Billing API
        Limit can range between 1 and 100, default is 10
        """
        return self.api.Product.list(limit=limit)

    def delete_product(self, product_id):
        """
        Delete a product resource via Billing API
        """
        return self.api.Product.delete(product_id)

    def search_products(self, query, limit=10):
        """
        Search for product resources via Billing API
        example: query="active:'true'"
        """
        return self.api.Product.search(query=query, limit=limit)

    def sync_product(self, subscription_product):
        """
        Synchronize a product resource via Billing API with a
        subscription product from the database.
        """
        product = self.create_or_update_product(
            name=subscription_product.product_name,
            description=subscription_product.description,
            # See Stripe docs for tax codes. https://stripe.com/docs/tax/tax-categories
            tax_code=subscription_product.tax_code,
            unit_label="user",
        )
        subscription_product.product_id = product["id"]

    def create_or_update_price(self, unit_amount, currency, product_id, tax_behavior):
        """
        Create price resource via Billing API, or update an active price
        resource with the same product and currency
        """
        # Search for active price that match all non-updatable fields.
        # (a) Use query fields supported by Stripe API.
        #     https://stripe.com/docs/search#query-fields-for-prices
        price_search = self.search_prices(
            f'active:"true" product:"{product_id}" currency:"{currency}"'
        )
        # (b) Filter for other fields not supported by Stripe API.
        prices = [p for p in price_search["data"] if p["unit_amount"] == unit_amount]
        # Create new price if no match found.
        if not prices:
            return self.create_price(
                unit_amount,
                currency,
                product_id,
                tax_behavior,
            )
        # Update most recent matching price and archive other matching prices.
        # https://stripe.com/docs/api/prices/update
        [*others, price] = sorted(prices, key=lambda p: p["created"])
        for other in others:
            self.update_price(other["id"], active=False)
        return self.update_price(price["id"], tax_behavior=tax_behavior)

    def create_price(self, unit_amount, currency, product_id, tax_behavior):
        """
        Create and return a price resource via Billing API
        """
        return self.api.Price.create(
            unit_amount=unit_amount,
            currency=currency,
            recurring={
                # Hardcode 1 month. Different interval does not make sense with metered.
                "interval": "month",
                # Set "metered" and "max" to enable Stripe usage records.
                # https://stripe.com/docs/products-prices/pricing-models#aggregate-metered-usage
                "usage_type": "metered",
                "aggregate_usage": "max",
            },
            product=product_id,
            tax_behavior=tax_behavior,
            metadata={"billing_service": "pypi", "domain": self.domain},
        )

    def retrieve_price(self, price_id):
        """
        Get a price resource via Billing API
        """
        return self.api.Price.retrieve(price_id)

    def update_price(self, price_id, **parameters):
        """
        Update a price resource by id via Billing API
        only allowing update of those attributes we use
        return the updated price
        """
        return self.api.Price.modify(price_id, **parameters)

    def list_all_prices(self, limit=10):
        """
        Get list of all price resources via Billing API
        Limit can range between 1 and 100, default is 10
        """
        return self.api.Price.list(limit=limit)

    def search_prices(self, query, limit=10):
        """
        Search for price resources via Billing API
        example: query="active:'true'"
        """
        return self.api.Price.search(query=query, limit=limit)

    def sync_price(self, subscription_price):
        """
        Synchronize a price resource via Billing API with a
        subscription price from the database.
        """
        price = self.create_or_update_price(
            unit_amount=subscription_price.unit_amount,
            currency=subscription_price.currency,
            product_id=subscription_price.subscription_product.product_id,
            tax_behavior=subscription_price.tax_behavior,
        )
        subscription_price.price_id = price["id"]

    def cancel_subscription(self, subscription_id):
        """
        Cancels a customer’s subscription immediately.
        The customer will not be charged again for the subscription.
        """
        return self.api.Subscription.delete(subscription_id)

    def create_or_update_usage_record(
        self, subscription_item_id, organization_member_count
    ):
        """
        Creates a usage record via Billing API
        for a specified subscription item and date with default=now,
        and fills it with a quantity=number of members in the org.
        """
        return self.api.SubscriptionItem.create_usage_record(
            subscription_item_id,
            action="set",
            quantity=organization_member_count,
        )


@implementer(IBillingService)
class MockStripeBillingService(GenericBillingService):
    @classmethod
    def create_service(cls, context, request):
        # Override api_base to hit mock-stripe in development
        stripe.api_base = request.registry.settings["billing.api_base"]
        stripe.api_version = request.registry.settings["billing.api_version"]
        stripe.api_key = "sk_test_123"
        publishable_key = "pk_test_123"
        webhook_secret = "whsec_123"
        domain = "localhost"

        return cls(stripe, publishable_key, webhook_secret, domain)

    def create_customer(self, name, description):
        # Mock Stripe doesn't return a customer_id so create a mock id by default
        customer = super().create_customer(name, description)
        customer["id"] = "mockcus_" + "".join(
            random.choices(digits + ascii_letters, k=14)
        )
        return customer

    def get_checkout_session(self, session_id, mock_checkout_session={}, **kwargs):
        # Mock Stripe doesn't persist data so allow passing in a mock_checkout_session.
        checkout_session = super().get_checkout_session(session_id)
        # Fill in customer ID, status, and subscription ID from mock_checkout_session.
        checkout_session["customer"]["id"] = mock_checkout_session.get(
            "customer", checkout_session["customer"]["id"]
        )
        checkout_session["customer"]["email"] = mock_checkout_session.get(
            "customer_email", checkout_session["customer"]["email"]
        )
        checkout_session["status"] = mock_checkout_session.get(
            "status", checkout_session["status"]
        )
        checkout_session["subscription"]["id"] = mock_checkout_session.get(
            "subscription", checkout_session["subscription"]["id"]
        )
        return checkout_session


@implementer(IBillingService)
class StripeBillingService(GenericBillingService):
    @classmethod
    def create_service(cls, context, request):
        stripe.api_version = request.registry.settings["billing.api_version"]
        stripe.api_key = request.registry.settings["billing.secret_key"]
        publishable_key = request.registry.settings["billing.publishable_key"]
        webhook_secret = request.registry.settings["billing.webhook_key"]
        domain = request.registry.settings["billing.domain"]

        return cls(stripe, publishable_key, webhook_secret, domain)


@implementer(ISubscriptionService)
class StripeSubscriptionService:
    def __init__(self, db_session):
        self.db = db_session

    def get_subscription(self, id):
        """
        Get a subscription by id
        """
        return self.db.get(StripeSubscription, id)

    def find_subscriptionid(self, subscription_id):
        """
        Find the unique subscription identifier for the subscription,
        by the payment service provider subscription id or None
        """
        try:
            (id,) = (
                self.db.query(StripeSubscription.id)
                .filter(
                    StripeSubscription.subscription_id == subscription_id,
                )
                .one()
            )
        except NoResultFound:
            return

        return id

    def add_subscription(
        self, customer_id, subscription_id, subscription_item_id, billing_email
    ):
        """
        Attempts to create a subscription object for the organization
        with the specified customer ID and subscription ID
        """
        # Get default subscription price.
        subscription_price = self.get_or_create_default_subscription_price()

        # Get the stripe customer.
        stripe_customer = self.get_stripe_customer(
            self.find_stripe_customer_id(customer_id)
        )

        # Set the billing email
        stripe_customer.billing_email = billing_email

        # Add new subscription.
        subscription = StripeSubscription(
            stripe_customer_id=stripe_customer.id,
            subscription_id=subscription_id,
            subscription_price_id=subscription_price.id,
            status=StripeSubscriptionStatus.Active,  # default active subscription
        )

        # Get the organization stripe customer.
        organization_stripe_customer = (
            self.db.query(OrganizationStripeCustomer)
            .filter(OrganizationStripeCustomer.stripe_customer_id == stripe_customer.id)
            .one()
        )

        # Link to organization.
        organization_subscription = OrganizationStripeSubscription(
            organization=organization_stripe_customer.organization,
            subscription=subscription,
        )

        self.db.add(subscription)
        self.db.add(organization_subscription)
        self.db.flush()  # flush db now so we have acccess to subscription.id

        # Create new subscription item.
        subscription_item = StripeSubscriptionItem(
            subscription_item_id=subscription_item_id,
            subscription_id=subscription.id,
            subscription_price_id=subscription_price.id,
            quantity=len(organization_stripe_customer.organization.users),
        )

        self.db.add(subscription_item)

        return subscription

    def update_subscription_status(self, id, status):
        """
        Update the status of a subscription object by subscription.id
        """
        self.db.query(StripeSubscription).filter(
            StripeSubscription.id == id,
        ).update({StripeSubscription.status: status})

    def delete_subscription(self, id):
        """
        Delete a subscription by ID
        """
        subscription = self.get_subscription(id)

        # Delete link to organization
        self.db.query(OrganizationStripeSubscription).filter_by(
            subscription=subscription
        ).delete()

        # Delete subscription items
        self.db.query(StripeSubscriptionItem).filter_by(
            subscription=subscription
        ).delete()

        self.db.delete(subscription)

    def get_subscriptions_by_customer(self, customer_id):
        """
        Get a list of subscriptions tied to the given customer ID
        """
        stripe_customer_id = self.find_stripe_customer_id(customer_id)
        return (
            self.db.query(StripeSubscription)
            .filter(StripeSubscription.stripe_customer_id == stripe_customer_id)
            .all()
        )

    def get_stripe_customer(self, stripe_customer_id):
        """
        Get a stripe customer by id
        """
        return self.db.get(StripeCustomer, stripe_customer_id)

    def find_stripe_customer_id(self, customer_id):
        """
        Get the stripe customer UUID tied to the given customer ID
        """
        try:
            (id,) = (
                self.db.query(StripeCustomer.id)
                .filter(
                    StripeCustomer.customer_id == customer_id,
                )
                .one()
            )
        except NoResultFound:
            return

        return id

    def delete_customer(self, customer_id):
        """
        Deletes a customer and all associated subscription data
        """
        subscriptions = self.get_subscriptions_by_customer(customer_id)

        for subscription in subscriptions:
            self.delete_subscription(subscription.id)

        stripe_customer_id = self.find_stripe_customer_id(customer_id)
        # Delete OrganizationStripeCustomer association
        self.db.query(OrganizationStripeCustomer).filter(
            OrganizationStripeCustomer.stripe_customer_id == stripe_customer_id
        ).delete()

        # Delete StripeCustomer object
        self.db.query(StripeCustomer).filter(
            StripeCustomer.id == stripe_customer_id
        ).delete()

    def add_stripe_customer(self, customer_id):
        """
        Create a StripeCustomer object to associate to the Stripe customer ID
        """
        stripe_customer = StripeCustomer(
            customer_id=customer_id,
        )

        self.db.add(stripe_customer)
        self.db.flush()  # flush db now so we have access to stripe_customer.id

        return stripe_customer

    def update_customer_email(self, customer_id, billing_email):
        """
        Update the customer's billing email
        """
        stripe_customer_id = self.find_stripe_customer_id(customer_id)
        self.db.query(StripeCustomer).filter(
            StripeCustomer.id == stripe_customer_id,
        ).update({StripeCustomer.billing_email: billing_email})

    def get_subscription_product(self, subscription_product_id):
        """
        Get a product by subscription product id
        """
        return self.db.get(StripeSubscriptionProduct, subscription_product_id)

    def get_subscription_products(self):
        """
        Get a list of all products
        """
        return (
            self.db.query(StripeSubscriptionProduct)
            .order_by(StripeSubscriptionProduct.product_name)
            .all()
        )

    def find_subscription_productid(self, search_term):
        """
        Find the unique product identifier for the product name,
        product id or None if nothing is found
        """
        try:
            (subscription_product_id,) = (
                self.db.query(StripeSubscriptionProduct.id)
                .filter(
                    or_(
                        StripeSubscriptionProduct.product_name == search_term,
                        StripeSubscriptionProduct.product_id == search_term,
                    )
                )
                .one()
            )
        except NoResultFound:
            return

        return subscription_product_id

    def add_subscription_product(self, product_name, description, product_id, tax_code):
        """
        Add a subscription product
        """
        subscription_product = StripeSubscriptionProduct(
            product_name=product_name,
            description=description,
            product_id=product_id,
            tax_code=tax_code,
        )

        self.db.add(subscription_product)
        self.db.flush()  # flush db now so we have access to subscription_product.id

        return subscription_product

    def update_subscription_product(self, subscription_product_id, **changes):
        """
        Accepts a subscription product object
        and attempts an update with those attributes
        """
        subscription_product = self.get_subscription_product(subscription_product_id)
        for attr, value in changes.items():
            setattr(subscription_product, attr, value)

        return subscription_product

    def delete_subscription_product(self, subscription_product_id):
        """
        Delete a subscription product
        """
        subscription_product = self.get_subscription_product(subscription_product_id)

        self.db.delete(subscription_product)

    def get_or_create_default_subscription_price(self):
        """
        Get the default subscription price or initialize one if nothing is found
        """
        try:
            subscription_price = (
                self.db.query(StripeSubscriptionPrice)
                .filter(StripeSubscriptionPrice.is_active)
                .one()
            )
        except NoResultFound:
            subscription_product = self.add_subscription_product(
                product_name="PyPI",
                description="Organization account for companies",
                product_id=None,
                # See Stripe docs for tax codes. https://stripe.com/docs/tax/tax-categories # noqa: E501
                tax_code="txcd_10103001",  # Software as a service (SaaS) - business use
            )
            subscription_price = self.add_subscription_price(
                price_id=None,
                currency="usd",
                subscription_product_id=subscription_product.id,
                unit_amount=500,
                recurring=StripeSubscriptionPriceInterval.Month,
                tax_behavior="inclusive",
            )

        return subscription_price

    def get_subscription_price(self, subscription_price_id):
        """
        Get a subscription price by id
        """
        return self.db.get(StripeSubscriptionPrice, subscription_price_id)

    def get_subscription_prices(self):
        """
        Get a list of all subscription prices
        """
        return (
            self.db.query(StripeSubscriptionPrice)
            .order_by(StripeSubscriptionPrice.id)
            .all()
        )

    def find_subscription_priceid(self, search_term):
        """
        Find the unique price identifier for the price id,
        subscription product id or None if nothing is found
        """
        try:
            (subscription_price_id,) = (
                self.db.query(StripeSubscriptionPrice.id)
                .filter(
                    StripeSubscriptionPrice.price_id == search_term,
                )
                .one()
            )
        except NoResultFound:
            return

        return subscription_price_id

    def add_subscription_price(
        self,
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
        subscription_price = StripeSubscriptionPrice(
            price_id=price_id,
            currency=currency,
            subscription_product_id=subscription_product_id,
            unit_amount=unit_amount,
            recurring=recurring,
            tax_behavior=tax_behavior,
        )

        self.db.add(subscription_price)
        self.db.flush()  # flush db now so we have access to subscription_price.id

        return subscription_price

    def update_subscription_price(self, subscription_price_id, **changes):
        """
        Accepts a subscription price object
        and attempts an update with those attributes
        """
        subscription_price = self.get_subscription_price(subscription_price_id)
        for attr, value in changes.items():
            setattr(subscription_price, attr, value)

        return subscription_price

    def delete_subscription_price(self, subscription_price_id):
        """
        Delete a subscription price
        """
        subscription_price = self.get_subscription_price(subscription_price_id)

        self.db.delete(subscription_price)


def subscription_factory(context, request):
    return StripeSubscriptionService(request.db)
