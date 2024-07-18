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
import tempfile
from pathlib import Path

from pydantic import BaseModel, TypeAdapter
from typing import Literal
from pypi_attestations import Attestation

from warehouse.packaging import ISimpleStorage, File


class Publisher(BaseModel):
    kind: str
    """
    """

    claims: object
    """
    """

class AttestationBundle(BaseModel):
    publisher: Publisher
    """
    """

    attestations: list[Attestation]
    """
    Attestations are returned as an opaque
    """

class Provenance(BaseModel):
    version: Literal[1]
    """
    The provenance object's version, set to 1
    """

    attestation_bundles: list[AttestationBundle]



def get_provenance_digest(request, file: File) -> str | None:
    if not file.attestations:
        return

    publisher_url = file.publisher_url
    if not publisher_url:
        return  # # TODO(dm)

    provenance_file_path = generate_provenance_file(request, publisher_url, file)

    with Path(provenance_file_path).open("rb") as file_handler:
        provenance_digest = hashlib.file_digest(file_handler, "sha256")

    return provenance_digest.hexdigest()


def generate_provenance_file(request, publisher_url: str, file: File) -> str:

    storage = request.find_service(ISimpleStorage)
    publisher = Publisher(
        kind=publisher_url,
        claims={}  # TODO(dm)
    )

    attestation_bundle = AttestationBundle(
        publisher=publisher,
        attestations=[
            TypeAdapter(Attestation).validate_json(
                Path(release_attestation.attestation_path).read_text()
            )
            for release_attestation in file.attestations
        ]
    )

    provenance = Provenance(
        version=1,
        attestation_bundles=[attestation_bundle]
    )

    provenance_file_path = f"{file.path}.provenance"
    with tempfile.NamedTemporaryFile() as f:
        f.write(provenance.model_dump_json().encode("utf-8"))
        f.flush()

        storage.store(
            f"{file.path}.provenance",
            f.name,
        )

    return provenance_file_path
