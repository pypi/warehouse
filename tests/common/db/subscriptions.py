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

from warehouse.subscriptions.models import (
    Subscription,
    SubscriptionPrice,
    SubscriptionProduct,
)

from .base import WarehouseFactory


class SubscriptionProductFactory(WarehouseFactory):
    class Meta:
        model = SubscriptionProduct

    id = factory.Faker("uuid4", cast_to=None)
    product_id = "prod_123"
    product_name = factory.Faker("pystr", max_chars=12)
    description = factory.Faker("sentence")


class SubscriptionPriceFactory(WarehouseFactory):
    class Meta:
        model = SubscriptionPrice

    id = factory.Faker("uuid4", cast_to=None)
    price_id = "price_123"
    currency = "usd"
    unit_amount = 2500
    recurring = "month"

    subscription_product = factory.SubFactory(SubscriptionProductFactory)


class SubscriptionFactory(WarehouseFactory):
    class Meta:
        model = Subscription

    id = factory.Faker("uuid4", cast_to=None)
    customer_id = factory.Faker("uuid4")
    subscription_id = factory.Faker("uuid4")
    subscription_price = factory.SubFactory(SubscriptionPriceFactory)
    status = "active"
