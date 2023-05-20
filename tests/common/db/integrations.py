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

from warehouse.integrations.vulnerabilities.models import VulnerabilityRecord

from .base import WarehouseFactory
from .packaging import ReleaseFactory


class VulnerabilityRecordFactory(WarehouseFactory):
    class Meta:
        model = VulnerabilityRecord

    id = factory.Faker("word")
    source = factory.Faker("word")
    link = factory.Faker("uri")
    aliases = factory.Sequence(lambda n: "alias" + str(n))
    releases = factory.SubFactory(ReleaseFactory)
    details = factory.Faker("word")
    fixed_in = factory.Sequence(lambda n: str(n) + ".0")
