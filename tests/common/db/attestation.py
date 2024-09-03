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

from warehouse.attestations.models import Attestation

from .base import WarehouseFactory


class AttestationFactory(WarehouseFactory):
    class Meta:
        model = Attestation

    file = factory.SubFactory("tests.common.db.packaging.FileFactory")
    attestation_file_blake2_digest = factory.LazyAttribute(
        lambda o: hashlib.blake2b(o.file.filename.encode("utf8")).hexdigest()
    )
