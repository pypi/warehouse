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

from tests.common.db.base import WarehouseFactory
from tests.common.db.packaging import FileFactory
from warehouse.attestations.models import Provenance


class ProvenanceFactory(WarehouseFactory):
    class Meta:
        model = Provenance

    file = factory.SubFactory(FileFactory)
    # TODO(DM) Generate a better provenance mock
    provenance = {}
    provenance_digest = factory.LazyAttribute(
        lambda o: hashlib.sha256(o.file.filename.encode("utf8")).hexdigest()
    )
