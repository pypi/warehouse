# SPDX-License-Identifier: Apache-2.0

import importlib

import pretend
import pytest
import stripe

from zope.interface.verify import verifyClass

from warehouse.organizations.models import (
    OrganizationStripeCustomer,
    OrganizationStripeSubscription,
)
from warehouse.subscriptions import services
from warehouse.subscriptions.interfaces import IBillingService, ISubscriptionService
from warehouse.subscriptions.models import (
    StripeSubscriptionPrice,
    StripeSubscriptionPriceInterval,
    StripeSubscriptionStatus,
)
from warehouse.subscriptions.services import (
    GenericBillingService,
    MockStripeBillingService,
    StripeBillingService,
)

from ...common.db.organizations import (
    OrganizationFactory,
    OrganizationStripeCustomerFactory,
    OrganizationStripeSubscriptionFactory,
)
from ...common.db.subscriptions import (
    StripeCustomerFactory,
    StripeSubscriptionFactory,
    StripeSubscriptionPriceFactory,
    StripeSubscriptionProductFactory,
)


class TestStripeBillingService:
    def test_verify_service(self):
        assert verifyClass(IBillingService, StripeBillingService)

    def test_basic_init(self):
        api = pretend.stub()

        billing_service = StripeBillingService(
            api=api,
            publishable_key="secret_to_everybody",
            webhook_secret="keep_it_secret_keep_it_safe",
            domain="tests",
        )

        assert billing_service.api is api
        assert billing_service.publishable_key == "secret_to_everybody"
        assert billing_service.webhook_secret == "keep_it_secret_keep_it_safe"
        assert billing_service.domain == "tests"

    def test_create_service(self):
        # Reload stripe to reset the global stripe.api_key to default.
        importlib.reload(stripe)

        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "billing.api_base": "http://localhost:12111",
                    "billing.api_version": "2020-08-27",
                    "billing.secret_key": "sk_test_123",
                    "billing.publishable_key": "pk_test_123",
                    "billing.webhook_key": "whsec_123",
                    "billing.domain": "tests",
                }
            )
        )
        billing_service = StripeBillingService.create_service(None, request)
        # Assert api_base isn't overwritten with mock service even if we try
        assert not billing_service.api.api_base == "http://localhost:12111"
        assert billing_service.api.api_version == "2020-08-27"
        assert billing_service.api.api_key == "sk_test_123"
        assert billing_service.publishable_key == "pk_test_123"
        assert billing_service.webhook_secret == "whsec_123"
        assert billing_service.domain == "tests"


class TestMockStripeBillingService:
    def test_verify_service(self):
        assert verifyClass(IBillingService, MockStripeBillingService)

    def test_basic_init(self):
        api = pretend.stub()

        billing_service = MockStripeBillingService(
            api=api,
            publishable_key="secret_to_everybody",
            webhook_secret="keep_it_secret_keep_it_safe",
            domain="tests",
        )

        assert billing_service.api is api
        assert billing_service.publishable_key == "secret_to_everybody"
        assert billing_service.webhook_secret == "keep_it_secret_keep_it_safe"
        assert billing_service.domain == "tests"

    def test_create_service(self):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "billing.api_base": "http://localhost:12111",
                    "billing.api_version": "2020-08-27",
                    "billing.secret_key": "sk_test_123",
                    "billing.publishable_key": "pk_test_123",
                    "billing.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = MockStripeBillingService.create_service(None, request)
        assert billing_service.api.api_base == "http://localhost:12111"
        assert billing_service.api.api_version == "2020-08-27"
        assert billing_service.api.api_key == "sk_test_123"
        assert billing_service.publishable_key == "pk_test_123"
        assert billing_service.webhook_secret == "whsec_123"

    def test_get_checkout_session(self, billing_service):
        random_session = billing_service.api.checkout.Session.list(limit=1)

        assert random_session.data[0].object == "checkout.session"

        retrieved_session = billing_service.get_checkout_session(
            random_session.data[0].id
        )

        assert retrieved_session.id == random_session.data[0].id

    def test_get_customer(self, billing_service, subscription_service):
        customer = billing_service.get_customer(subscription_id="sub_12345")

        assert customer is not None
        assert customer["id"]

    def test_create_customer(self, billing_service, organization_service):
        organization = OrganizationFactory.create()

        customer = billing_service.create_customer(
            name=organization.name,
            description=organization.description,
        )

        assert customer is not None
        assert customer["id"]

    def test_update_customer(self, billing_service, organization_service):
        organization = OrganizationFactory.create()

        customer = billing_service.create_customer(
            name=organization.name,
            description=organization.description,
        )

        assert customer is not None
        assert customer["name"] == organization.name

        customer = billing_service.update_customer(
            customer_id=customer["id"],
            name="wutangClan",
            description=organization.description,
        )

        assert customer is not None
        assert customer["name"] == "wutangClan"

    def test_create_checkout_session(self, billing_service, subscription_service):
        subscription_price = StripeSubscriptionPriceFactory.create()
        success_url = "http://what.ever"
        cancel_url = "http://no.way"

        checkout_session = billing_service.create_checkout_session(
            customer_id="cus_123",
            price_ids=[subscription_price.price_id],
            success_url=success_url,
            cancel_url=cancel_url,
        )

        assert checkout_session.id is not None

    def test_create_portal_session(self, billing_service):
        return_url = "http://return.url"

        session_url = billing_service.create_portal_session(
            customer_id="cus_123",
            return_url=return_url,
        )
        assert session_url is not None

    def test_webhook_received(self, billing_service, monkeypatch):
        payload = pretend.stub()
        sig_header = pretend.stub()

        construct_event = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(stripe.Webhook, "construct_event", construct_event)

        billing_service.webhook_received(payload, sig_header)

        assert construct_event.calls == [
            pretend.call(payload, sig_header, billing_service.webhook_secret),
        ]

    def test_create_or_update_product(
        self, billing_service, subscription_service, monkeypatch
    ):
        subscription_product = StripeSubscriptionProductFactory.create()

        search_products = pretend.call_recorder(
            lambda *a, **kw: {
                "data": [
                    {
                        "id": str(subscription_product.id),
                        "name": subscription_product.product_name,
                        "created": 0,
                    },
                ],
            }
        )
        monkeypatch.setattr(billing_service, "search_products", search_products)

        product = billing_service.create_or_update_product(
            name=subscription_product.product_name,
            description=subscription_product.description,
            tax_code=subscription_product.tax_code,
            unit_label="user",
        )

        assert product is not None

    def test_create_or_update_product_new_product(self, billing_service, monkeypatch):
        search_products = pretend.call_recorder(lambda *a, **kw: {"data": []})
        monkeypatch.setattr(billing_service, "search_products", search_products)

        product = billing_service.create_or_update_product(
            name="Vitamin PyPI",
            description="Take two and call me in the morning.",
            tax_code="txcd_10103001",  # "Software as a service (SaaS) - business use"
            unit_label="user",
        )

        assert product is not None

    def test_create_product(self, billing_service, subscription_service):
        subscription_product = StripeSubscriptionProductFactory.create()

        product = billing_service.create_product(
            name=subscription_product.product_name,
            description=subscription_product.description,
            tax_code=subscription_product.tax_code,
            unit_label="user",
        )

        assert product is not None

    def test_retrieve_product(self, billing_service, subscription_service):
        subscription_product = StripeSubscriptionProductFactory.create()

        product = billing_service.retrieve_product(
            product_id=subscription_product.product_id,
        )

        assert product is not None

    def test_update_product(self, billing_service, subscription_service):
        subscription_product = StripeSubscriptionProductFactory.create()

        product = billing_service.update_product(
            product_id=subscription_product.product_id,
            name=subscription_product.product_name,
            description=subscription_product.description,
            tax_code=subscription_product.tax_code,
            unit_label="user",
        )

        # stripe-mock has no persistence so we can't really check if we're
        # updating the object or not, so just make sure we got one back
        assert product is not None

    def test_list_all_products(self, billing_service):
        products = billing_service.list_all_products()

        assert products is not None

    def test_delete_product(self, billing_service, subscription_service):
        subscription_product = StripeSubscriptionProductFactory.create()

        product = billing_service.delete_product(
            product_id=subscription_product.product_id
        )
        assert product.deleted

    def test_search_products(self, billing_service):
        products = billing_service.search_products(query="active:'true'")

        assert products is not None

    def test_create_price(self, billing_service, subscription_service):
        subscription_price = StripeSubscriptionPriceFactory.create()

        price = billing_service.create_price(
            unit_amount=subscription_price.unit_amount,
            currency=subscription_price.currency,
            product_id=subscription_price.subscription_product.id,
            tax_behavior=subscription_price.tax_behavior,
        )

        assert price is not None

    def test_retrieve_price(self, billing_service, subscription_service):
        subscription_price = StripeSubscriptionPriceFactory.create()

        price = billing_service.retrieve_price(
            price_id=subscription_price.price_id,
        )

        assert price is not None

    def test_update_price(self, billing_service, subscription_service):
        subscription_price = StripeSubscriptionPriceFactory.create()

        price = billing_service.update_price(
            price_id=subscription_price.price_id,
            active="false",
        )

        assert not price.active

    def test_list_all_prices(self, billing_service):
        prices = billing_service.list_all_prices()

        assert prices is not None

    def test_search_prices(self, billing_service):
        prices = billing_service.search_prices(query="active:'true'")

        assert prices is not None

    def test_create_or_update_price(
        self, billing_service, subscription_service, monkeypatch
    ):
        subscription_price = StripeSubscriptionPriceFactory.create()
        price = {
            "id": "price_1",
            "unit_amount": subscription_price.unit_amount,
            "currency": subscription_price.currency,
            "recurring": {
                "interval": "month",
                "usage_type": "metered",
                "aggregate_usage": "max",
            },
            "product_id": subscription_price.subscription_product.id,
            "tax_behavior": subscription_price.tax_behavior,
            "created": 1,
        }
        other = {
            "id": "price_0",
            "unit_amount": subscription_price.unit_amount,
            "currency": subscription_price.currency,
            "recurring": {
                "interval": "month",
                "usage_type": "metered",
                "aggregate_usage": "max",
            },
            "product_id": subscription_price.subscription_product.id,
            "tax_behavior": subscription_price.tax_behavior,
            "created": 0,
        }
        monkeypatch.setattr(
            billing_service, "search_prices", lambda *a, **kw: {"data": [price, other]}
        )

        price = billing_service.create_or_update_price(
            unit_amount=subscription_price.unit_amount,
            currency=subscription_price.currency,
            product_id=subscription_price.subscription_product.id,
            tax_behavior=subscription_price.tax_behavior,
        )

        assert price["id"] == "price_1"

    def test_cancel_subscription(self, billing_service, subscription_service):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        db_subscription = StripeSubscriptionFactory.create(customer=stripe_customer)

        subscription = billing_service.cancel_subscription(
            subscription_id=db_subscription.subscription_id
        )

        # I would check to ensure the status is Canceled but mock stripe
        # doesn't care enough to update the status for whatever reason ¯\_(ツ)_/¯
        assert subscription.status is not None

    def test_create_or_update_usage_record(self, billing_service, subscription_service):
        result = billing_service.create_or_update_usage_record("si_1234", 5)

        # Ensure we got a record back with the subscription_item and quantity
        assert result.id
        assert result.subscription_item == "si_1234"
        assert result.quantity == 5


class TestGenericBillingService:
    def test_basic_init(self):
        api = pretend.stub()

        billing_service = GenericBillingService(
            api=api,
            publishable_key="secret_to_everybody",
            webhook_secret="keep_it_secret_keep_it_safe",
            domain="tests",
        )

        assert billing_service.api is api
        assert billing_service.publishable_key == "secret_to_everybody"
        assert billing_service.webhook_secret == "keep_it_secret_keep_it_safe"
        assert billing_service.domain == "tests"

    def test_notimplementederror(self):
        with pytest.raises(NotImplementedError):
            GenericBillingService.create_service(pretend.stub(), pretend.stub())


def test_subscription_factory():
    db = pretend.stub()
    context = pretend.stub()
    request = pretend.stub(db=db)

    service = services.subscription_factory(context, request)
    assert service.db is db


class TestStripeSubscriptionService:
    def test_verify_service(self):
        assert verifyClass(ISubscriptionService, services.StripeSubscriptionService)

    def test_service_creation(self):
        session = pretend.stub()
        service = services.StripeSubscriptionService(session)

        assert service.db is session

    def test_find_subscriptionid_nonexistent_sub(self, subscription_service):
        assert subscription_service.find_subscriptionid("fake_news") is None

    def test_find_subscriptionid(self, subscription_service):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = StripeSubscriptionFactory.create(customer=stripe_customer)

        assert (
            subscription_service.find_subscriptionid(subscription.subscription_id)
            == subscription.id
        )

    def test_add_subscription(self, billing_service, subscription_service):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )

        new_subscription = subscription_service.add_subscription(
            customer_id=stripe_customer.customer_id,
            subscription_id="sub_12345",
            subscription_item_id="si_12345",
            billing_email="good@day.com",
        )

        subscription_service.db.flush()

        subscription_from_db = subscription_service.get_subscription(
            new_subscription.id
        )

        assert (
            subscription_from_db.customer.customer_id
            == new_subscription.customer.customer_id
        )
        assert subscription_from_db.subscription_id == new_subscription.subscription_id
        assert (
            subscription_from_db.subscription_price_id
            == new_subscription.subscription_price_id
        )
        assert subscription_from_db.status == StripeSubscriptionStatus.Active.value
        assert stripe_customer.billing_email == "good@day.com"

    def test_update_subscription_status(self, subscription_service, db_request):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = StripeSubscriptionFactory.create(customer=stripe_customer)

        assert subscription.status == StripeSubscriptionStatus.Active.value

        subscription_service.update_subscription_status(
            subscription.id,
            status=StripeSubscriptionStatus.Active.value,
        )

        assert subscription.status == StripeSubscriptionStatus.Active.value

    def test_delete_subscription(self, subscription_service, db_request):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = StripeSubscriptionFactory.create(customer=stripe_customer)
        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )

        subscription_service.delete_subscription(subscription.id)
        subscription_service.db.flush()

        assert subscription_service.get_subscription(subscription.id) is None
        assert not (
            db_request.db.query(OrganizationStripeSubscription)
            .filter_by(subscription=subscription)
            .count()
        )

    def test_get_subscriptions_by_customer(self, subscription_service):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = StripeSubscriptionFactory.create(customer=stripe_customer)
        subscription1 = StripeSubscriptionFactory.create(customer=stripe_customer)

        subscriptions = subscription_service.get_subscriptions_by_customer(
            stripe_customer.customer_id
        )

        assert subscription in subscriptions
        assert subscription1 in subscriptions

    def test_delete_customer(self, subscription_service, db_request):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = StripeSubscriptionFactory.create(customer=stripe_customer)
        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )
        subscription1 = StripeSubscriptionFactory.create(customer=stripe_customer)
        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription1
        )

        subscription_service.delete_customer(stripe_customer.customer_id)

        assert subscription_service.get_subscription(subscription.id) is None
        assert not (
            db_request.db.query(OrganizationStripeSubscription)
            .filter_by(subscription=subscription)
            .count()
        )
        assert subscription_service.get_subscription(subscription1.id) is None
        assert not (
            db_request.db.query(OrganizationStripeSubscription)
            .filter_by(subscription=subscription1)
            .count()
        )
        # assert not
        assert not (
            db_request.db.query(OrganizationStripeCustomer)
            .filter_by(organization=organization)
            .count()
        )

    def test_update_customer_email(self, subscription_service, db_request):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )

        subscription_service.update_customer_email(
            stripe_customer.customer_id,
            billing_email="great@day.com",
        )

        assert stripe_customer.billing_email == "great@day.com"

    def test_get_subscription_products(self, subscription_service):
        subscription_product = StripeSubscriptionProductFactory.create()
        subscription_product_deux = StripeSubscriptionProductFactory.create()
        subscription_products = subscription_service.get_subscription_products()

        assert subscription_product in subscription_products
        assert subscription_product_deux in subscription_products

    def test_find_subscription_productid_nonexistent_prod(self, subscription_service):
        assert subscription_service.find_subscription_productid("can't_see_me") is None

    def test_find_subscription_productid(self, subscription_service):
        subscription_product = StripeSubscriptionProductFactory.create()
        assert (
            subscription_service.find_subscription_productid(
                subscription_product.product_name
            )
            == subscription_product.id
        )
        assert (
            subscription_service.find_subscription_productid(
                subscription_product.product_id
            )
            == subscription_product.id
        )

    def test_add_subscription_product(self, subscription_service):
        subscription_product = StripeSubscriptionProductFactory.create()

        new_subscription_product = subscription_service.add_subscription_product(
            product_name=subscription_product.product_name,
            description=subscription_product.description,
            product_id=subscription_product.product_id,
            tax_code=subscription_product.tax_code,
        )
        subscription_service.db.flush()
        product_from_db = subscription_service.get_subscription_product(
            new_subscription_product.id
        )

        assert product_from_db.product_name == subscription_product.product_name
        assert product_from_db.description == subscription_product.description
        assert product_from_db.product_id == subscription_product.product_id
        assert product_from_db.tax_code == subscription_product.tax_code
        assert product_from_db.is_active

    def test_update_subscription_product(self, subscription_service, db_request):
        subscription_product = StripeSubscriptionProductFactory.create(
            product_name="original_name"
        )

        subscription_service.update_subscription_product(
            subscription_product.id,
            product_name="updated_product_name",
        )

        db_subscription_product = subscription_service.get_subscription_product(
            subscription_product.id
        )

        assert db_subscription_product.product_name == "updated_product_name"

    def test_delete_subscription_product(self, subscription_service):
        subscription_product = StripeSubscriptionProductFactory.create()

        subscription_service.delete_subscription_product(subscription_product.id)
        subscription_service.db.flush()

        assert (
            subscription_service.get_subscription_product(subscription_product.id)
            is None
        )

    def test_get_subscription_prices(self, subscription_service):
        subscription_price = StripeSubscriptionPriceFactory.create()
        subscription_price_deux = StripeSubscriptionPriceFactory.create()
        subscription_prices = subscription_service.get_subscription_prices()

        assert subscription_price in subscription_prices
        assert subscription_price_deux in subscription_prices

    def test_find_subscriptionid_nonexistent_price(self, subscription_service):
        assert subscription_service.find_subscription_priceid("john_cena") is None

    def test_add_subscription_price(self, subscription_service, db_request):
        subscription_product = StripeSubscriptionProductFactory.create()

        subscription_service.add_subscription_price(
            "price_321",
            "usd",
            subscription_product.id,
            1500,
            StripeSubscriptionPriceInterval.Month.value,
            "taxerrific",
        )

        subscription_price_id = subscription_service.find_subscription_priceid(
            "price_321"
        )
        subscription_price = subscription_service.get_subscription_price(
            subscription_price_id
        )

        assert subscription_price.is_active
        assert subscription_price.price_id == "price_321"
        assert subscription_price.currency == "usd"
        assert subscription_price.subscription_product_id == subscription_product.id
        assert subscription_price.unit_amount == 1500
        assert (
            subscription_price.recurring == StripeSubscriptionPriceInterval.Month.value
        )
        assert subscription_price.tax_behavior == "taxerrific"

    def test_update_subscription_price(self, subscription_service, db_request):
        subscription_price = StripeSubscriptionPriceFactory.create()

        assert subscription_price.price_id == "price_123"
        assert (
            subscription_price.recurring == StripeSubscriptionPriceInterval.Month.value
        )

        subscription_service.update_subscription_price(
            subscription_price.id,
            price_id="price_321",
            recurring=StripeSubscriptionPriceInterval.Year.value,
        )

        assert subscription_price.price_id == "price_321"
        assert (
            subscription_price.recurring == StripeSubscriptionPriceInterval.Year.value
        )

        db_subscription_price = subscription_service.get_subscription_price(
            subscription_price.id
        )
        assert db_subscription_price.price_id == "price_321"
        assert (
            db_subscription_price.recurring
            == StripeSubscriptionPriceInterval.Year.value
        )

    def test_delete_subscription_price(self, subscription_service, db_request):
        """
        Delete a subscription price
        """
        subscription_price = StripeSubscriptionPriceFactory.create()

        assert db_request.db.get(StripeSubscriptionPrice, subscription_price.id)

        subscription_service.delete_subscription_price(subscription_price.id)
        subscription_service.db.flush()

        assert not (db_request.db.get(StripeSubscriptionPrice, subscription_price.id))
