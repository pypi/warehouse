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

import pretend
import pytest

from zope.interface.verify import verifyClass

from warehouse.subscriptions import services
from warehouse.subscriptions.interfaces import IBillingService, ISubscriptionService
from warehouse.subscriptions.models import (
    SubscriptionPrice,
    SubscriptionPriceInterval,
    SubscriptionStatus,
)
from warehouse.subscriptions.services import (
    GenericBillingService,
    LocalBillingService,
    StripeBillingService,
)

from ...common.db.subscriptions import (
    SubscriptionFactory,
    SubscriptionPriceFactory,
    SubscriptionProductFactory,
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
        )

        assert billing_service.api is api
        assert billing_service.publishable_key == "secret_to_everybody"
        assert billing_service.webhook_secret == "keep_it_secret_keep_it_safe"

    def test_create_service(self):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://stripe:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = StripeBillingService.create_service(None, request)
        # Assert api_base isn't overwritten with mock service even if we try
        assert not billing_service.api.api_base == "http://stripe:12111"
        assert billing_service.api.api_key == "sk_test_123"
        assert billing_service.publishable_key == "pk_test_123"
        assert billing_service.webhook_secret == "whsec_123"


class TestLocalBillingService:
    def test_verify_service(self):
        assert verifyClass(IBillingService, LocalBillingService)

    def test_basic_init(self):
        api = pretend.stub()

        billing_service = LocalBillingService(
            api=api,
            publishable_key="secret_to_everybody",
            webhook_secret="keep_it_secret_keep_it_safe",
        )

        assert billing_service.api is api
        assert billing_service.publishable_key == "secret_to_everybody"
        assert billing_service.webhook_secret == "keep_it_secret_keep_it_safe"

    def test_create_service(self):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://stripe:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = LocalBillingService.create_service(None, request)
        assert billing_service.api.api_base == "http://stripe:12111"
        assert billing_service.api.api_key == "sk_test_123"
        assert billing_service.publishable_key == "pk_test_123"
        assert billing_service.webhook_secret == "whsec_123"

    def test_get_checkout_session(self):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://stripe:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = LocalBillingService.create_service(None, request)

        assert billing_service.api.api_key == "sk_test_123"

        random_session = billing_service.api.checkout.Session.list(limit=1)

        assert random_session.data[0].object == "checkout.session"

        retrieved_session = billing_service.get_checkout_session(
            random_session.data[0].id
        )

        assert retrieved_session.id == random_session.data[0].id

    def test_create_checkout_session(self, subscription_service):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://stripe:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = LocalBillingService.create_service(None, request)
        subscription_price = SubscriptionPriceFactory.create()
        success_url = "http://what.ever"
        cancel_url = "http://no.way"

        checkout_session = billing_service.create_checkout_session(
            price_id=subscription_price.price_id,
            success_url=success_url,
            cancel_url=cancel_url,
        )

        assert checkout_session.id is not None
        # assert checkout_session.url is not None

    def test_create_portal_session(self):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://stripe:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = LocalBillingService.create_service(None, request)
        return_url = "http://return.url"

        session_url = billing_service.create_portal_session(
            customer_id="cus_123",
            return_url=return_url,
        )
        assert session_url is not None

    def test_webhook_received(self):
        with pytest.raises(NotImplementedError):
            request = pretend.stub(
                registry=pretend.stub(
                    settings={
                        "subscription.api_base": "http://stripe:12111",
                        "subscription.secret_key": "sk_test_123",
                        "subscription.publishable_key": "pk_test_123",
                        "subscription.webhook_key": "whsec_123",
                    }
                )
            )
            billing_service = LocalBillingService.create_service(None, request)
            billing_service.webhook_received(request)

    def test_create_product(self, subscription_service):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://stripe:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = LocalBillingService.create_service(None, request)
        subscription_product = SubscriptionProductFactory.create()

        product = billing_service.create_product(
            name=subscription_product.product_name,
            description=subscription_product.description,
            tax_code=subscription_product.tax_code,
        )

        assert product is not None

    def test_retrieve_product(self, subscription_service):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://stripe:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = LocalBillingService.create_service(None, request)
        subscription_product = SubscriptionProductFactory.create()

        product = billing_service.retrieve_product(
            product_id=subscription_product.product_id,
        )

        assert product is not None

    def test_update_product(self, subscription_service):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://stripe:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = LocalBillingService.create_service(None, request)
        subscription_product = SubscriptionProductFactory.create()

        product = billing_service.update_product(
            product_id=subscription_product.product_id,
            name=subscription_product.product_name,
            description=subscription_product.description,
            tax_code=subscription_product.tax_code,
        )

        # stripe-mock has no persistence so we can't really check if we're
        # updating the object or not, so just make sure we got one back
        assert product is not None

    def test_list_all_products(self):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://stripe:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = LocalBillingService.create_service(None, request)
        products = billing_service.list_all_products()

        assert products is not None

    def test_delete_product(self, subscription_service):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://stripe:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = LocalBillingService.create_service(None, request)
        subscription_product = SubscriptionProductFactory.create()

        product = billing_service.delete_product(
            product_id=subscription_product.product_id
        )
        assert product.deleted

    def test_search_products(self):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://stripe:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = LocalBillingService.create_service(None, request)
        products = billing_service.search_products(query="active:'true'")

        assert products is not None

    def test_create_price(self, subscription_service):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://stripe:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = LocalBillingService.create_service(None, request)
        subscription_price = SubscriptionPriceFactory.create()

        price = billing_service.create_price(
            unit_amount=subscription_price.unit_amount,
            currency=subscription_price.currency,
            recurring=subscription_price.recurring,
            product_id=subscription_price.subscription_product.id,
            tax_behavior=subscription_price.tax_behavior,
        )

        assert price is not None

    def test_retrieve_price(self, subscription_service):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://stripe:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = LocalBillingService.create_service(None, request)
        subscription_price = SubscriptionPriceFactory.create()

        price = billing_service.retrieve_price(
            price_id=subscription_price.price_id,
        )

        assert price is not None

    def test_update_price(self, subscription_service):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://stripe:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = LocalBillingService.create_service(None, request)
        subscription_price = SubscriptionPriceFactory.create()

        price = billing_service.update_price(
            price_id=subscription_price.price_id,
            active="false",
            tax_behavior=subscription_price.tax_behavior,
        )

        assert not price.active

    def test_list_all_prices(self):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://stripe:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = LocalBillingService.create_service(None, request)
        prices = billing_service.list_all_prices()

        assert prices is not None

    def test_search_prices(self):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://stripe:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = LocalBillingService.create_service(None, request)
        prices = billing_service.search_prices(query="active:'true'")

        assert prices is not None


class TestGenericBillingService:
    def test_basic_init(self):
        api = pretend.stub()

        billing_service = GenericBillingService(
            api=api,
            publishable_key="secret_to_everybody",
            webhook_secret="keep_it_secret_keep_it_safe",
        )

        assert billing_service.api is api
        assert billing_service.publishable_key == "secret_to_everybody"
        assert billing_service.webhook_secret == "keep_it_secret_keep_it_safe"

    def test_notimplementederror(self):
        with pytest.raises(NotImplementedError):
            GenericBillingService.create_service(pretend.stub(), pretend.stub())


def test_subscription_factory():
    db = pretend.stub()
    context = pretend.stub()
    request = pretend.stub(db=db)

    service = services.subscription_factory(context, request)
    assert service.db is db


class TestSubscriptionService:
    def test_verify_service(self):
        assert verifyClass(ISubscriptionService, services.SubscriptionService)

    def test_service_creation(self, remote_addr):
        session = pretend.stub()
        service = services.SubscriptionService(session)

        assert service.db is session

    def test_get_publishable_key(self, subscription_service):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://stripe:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = LocalBillingService.create_service(None, request)

        request = pretend.stub(
            find_service=pretend.call_recorder(lambda *args, **kwargs: billing_service),
        )

        pub_key = subscription_service.get_publishable_key(request)
        assert pub_key == "pk_test_123"

    def test_find_subscriptionid_nonexistent_sub(self, subscription_service):
        assert subscription_service.find_subscriptionid("fake_news") is None

    def test_find_subscriptionid(self, subscription_service):
        subscription = SubscriptionFactory.create()
        assert (
            subscription_service.find_subscriptionid(subscription.subscription_id)
            == subscription.id
        )

    def test_add_subscription(self, subscription_service):
        subscription_price = SubscriptionPriceFactory.create()

        new_subscription = subscription_service.add_subscription(
            customer_id="cus_12345",
            subscription_id="sub_12345",
            subscription_price_id=subscription_price.id,
        )

        subscription_service.db.flush()

        subscription_from_db = subscription_service.get_subscription(
            new_subscription.id
        )

        assert subscription_from_db.customer_id == new_subscription.customer_id
        assert subscription_from_db.subscription_id == new_subscription.subscription_id
        assert (
            subscription_from_db.subscription_price_id
            == new_subscription.subscription_price_id
        )
        assert subscription_from_db.status == SubscriptionStatus.Active.value

    def test_update_subscription_status(self, subscription_service, db_request):
        subscription = SubscriptionFactory.create()

        assert subscription.status == SubscriptionStatus.Active.value

        subscription_service.update_subscription_status(
            subscription.id,
            status=SubscriptionStatus.Active.value,
        )

        assert subscription.status == SubscriptionStatus.Active.value

    def test_get_subscription_products(self, subscription_service):
        subscription_product = SubscriptionProductFactory.create()
        subscription_product_deux = SubscriptionProductFactory.create()
        subscription_products = subscription_service.get_subscription_products()

        assert subscription_product in subscription_products
        assert subscription_product_deux in subscription_products

    def test_find_subscription_productid_nonexistent_prod(self, subscription_service):
        assert subscription_service.find_subscription_productid("can't_see_me") is None

    def test_find_subscription_productid(self, subscription_service):
        subscription_product = SubscriptionProductFactory.create()
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
        subscription_product = SubscriptionProductFactory.create()

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
        subscription_product = SubscriptionProductFactory.create(
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
        subscription_product = SubscriptionProductFactory.create()

        subscription_service.delete_subscription_product(subscription_product.id)

        assert (
            subscription_service.get_subscription_product(subscription_product.id)
            is None
        )

    def test_get_subscription_prices(self, subscription_service):
        subscription_price = SubscriptionPriceFactory.create()
        subscription_price_deux = SubscriptionPriceFactory.create()
        subscription_prices = subscription_service.get_subscription_prices()

        assert subscription_price in subscription_prices
        assert subscription_price_deux in subscription_prices

    def test_find_subscriptionid_nonexistent_price(self, subscription_service):
        assert subscription_service.find_subscription_priceid("john_cena") is None

    def test_add_subscription_price(self, subscription_service, db_request):
        subscription_product = SubscriptionProductFactory.create()

        subscription_service.add_subscription_price(
            "price_321",
            "usd",
            subscription_product.id,
            1500,
            SubscriptionPriceInterval.Month.value,
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
        assert subscription_price.recurring == SubscriptionPriceInterval.Month.value
        assert subscription_price.tax_behavior == "taxerrific"

    def test_update_subscription_price(self, subscription_service, db_request):
        subscription_price = SubscriptionPriceFactory.create()

        assert subscription_price.price_id == "price_123"
        assert subscription_price.recurring == SubscriptionPriceInterval.Month.value

        subscription_service.update_subscription_price(
            subscription_price.id,
            price_id="price_321",
            recurring=SubscriptionPriceInterval.Year.value,
        )

        assert subscription_price.price_id == "price_321"
        assert subscription_price.recurring == SubscriptionPriceInterval.Year.value

        db_subscription_price = subscription_service.get_subscription_price(
            subscription_price.id
        )
        assert db_subscription_price.price_id == "price_321"
        assert db_subscription_price.recurring == SubscriptionPriceInterval.Year.value

    def test_delete_subscription_price(self, subscription_service, db_request):
        """
        Delete a subscription price
        """
        subscription_price = SubscriptionPriceFactory.create()

        assert db_request.db.query(SubscriptionPrice).get(subscription_price.id)

        subscription_service.delete_subscription_price(subscription_price.id)

        assert not (db_request.db.query(SubscriptionPrice).get(subscription_price.id))
