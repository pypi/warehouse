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

import hashlib

import factory
import faker

from warehouse.ip_addresses.models import IpAddress

from .base import WarehouseFactory

fake = faker.Faker()


class IpAddressFactory(WarehouseFactory):
    class Meta:
        model = IpAddress

    # TODO: Replace when factory_boy supports `unique`.
    #  See https://github.com/FactoryBoy/factory_boy/pull/997
    ip_address = factory.Sequence(lambda _: fake.unique.ipv4_private())

    hashed_ip_address = factory.LazyAttribute(
        lambda o: hashlib.sha256(o.ip_address.encode("utf8")).hexdigest()
    )
