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

from warehouse.ip_addresses.models import IpAddress

from .base import UniqueFaker, WarehouseFactory


class IpAddressFactory(WarehouseFactory):
    class Meta:
        model = IpAddress

    ip_address = UniqueFaker("ipv4_private")
    hashed_ip_address = factory.LazyAttribute(
        lambda o: hashlib.sha256(o.ip_address.encode("utf8")).hexdigest()
    )
