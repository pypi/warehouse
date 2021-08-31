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

from datetime import date, timedelta

import factory

from warehouse.banners.models import Banner

from .base import WarehouseFactory


class BannerFactory(WarehouseFactory):
    class Meta:
        model = Banner

    name = factory.faker.Faker("word")
    text = factory.faker.Faker("text", max_nb_chars=30)
    link_url = factory.faker.Faker("url")
    link_label = factory.faker.Faker("text", max_nb_chars=10)

    active = True
    end = date.today() + timedelta(days=2)
