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

import factory
import faker

from warehouse.subscriptions.models import (
    StripeCustomer,
    StripeSubscription,
    StripeSubscriptionItem,
    StripeSubscriptionPrice,
    StripeSubscriptionProduct,
    StripeSubscriptionStatus,
)

from .base import WarehouseFactory

fake = faker.Faker()


class StripeCustomerFactory(WarehouseFactory):
    class Meta:
        model = StripeCustomer

    id = factory.Faker("uuid4", cast_to=None)
    customer_id = factory.Faker("uuid4")

    # TODO: Replace when factory_boy supports `unique`.
    #  See https://github.com/FactoryBoy/factory_boy/pull/997
    billing_email = factory.Sequence(lambda _: fake.unique.safe_email())


class StripeSubscriptionProductFactory(WarehouseFactory):
    class Meta:
        model = StripeSubscriptionProduct

    id = factory.Faker("uuid4", cast_to=None)
    product_id = "prod_123"
    product_name = factory.Faker("pystr", max_chars=12)
    description = factory.Faker("sentence")


class StripeSubscriptionPriceFactory(WarehouseFactory):
    class Meta:
        model = StripeSubscriptionPrice

    id = factory.Faker("uuid4", cast_to=None)
    price_id = "price_123"
    currency = "usd"
    unit_amount = 2500
    recurring = "month"

    subscription_product = factory.SubFactory(StripeSubscriptionProductFactory)


class StripeSubscriptionFactory(WarehouseFactory):
    class Meta:
        model = StripeSubscription

    id = factory.Faker("uuid4", cast_to=None)
    subscription_id = factory.Faker("uuid4")
    status = StripeSubscriptionStatus.Active

    subscription_price = factory.SubFactory(StripeSubscriptionPriceFactory)
    customer = factory.SubFactory(StripeCustomerFactory)


class StripeSubscriptionItemFactory(WarehouseFactory):
    class Meta:
        model = StripeSubscriptionItem

    id = factory.Faker("uuid4", cast_to=None)
    subscription_item_id = "si_123"
    quantity = 1

    subscription = factory.SubFactory(StripeSubscriptionFactory)
    subscription_price = factory.SubFactory(StripeSubscriptionPriceFactory)
