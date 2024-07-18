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
from typing import Literal

from pydantic import BaseModel, TypeAdapter
from pypi_attestations import Attestation

from warehouse.packaging import File, ISimpleStorage


class Publisher(BaseModel):
    kind: str
    """
    The kind of Trusted Publisher.
    """

    claims: object
    """
    Claims specified by the publisher.
    """


class AttestationBundle(BaseModel):
    publisher: Publisher
    """
    The publisher associated with this set of attestations.
    """

    attestations: list[Attestation]
    """
    The list of attestations included in this bundle.
    """


class Provenance(BaseModel):
    version: Literal[1]
    """
    The provenance object's version, which is always 1.
    """

    attestation_bundles: list[AttestationBundle]
    """
    One or more attestation "bundles".
    """


def get_provenance_digest(request, file: File) -> str | None:
    if not file.attestations:
        return None

    publisher_url = file.publisher_url
    if not publisher_url:
        return None  # TODO(dm)

    provenance_file_path, provenance_digest = generate_provenance_file(
        request, publisher_url, file
    )
    return provenance_digest


def generate_provenance_file(
    request, publisher_url: str, file: File
) -> tuple[Path, str]:

    storage = request.find_service(ISimpleStorage)
    publisher = Publisher(kind=publisher_url, claims={})  # TODO(dm)

    attestation_bundle = AttestationBundle(
        publisher=publisher,
        attestations=[
            TypeAdapter(Attestation).validate_json(
                Path(release_attestation.attestation_path).read_text()
            )
            for release_attestation in file.attestations
        ],
    )

    provenance = Provenance(version=1, attestation_bundles=[attestation_bundle])

    provenance_file_path = Path(f"{file.path}.provenance")
    with tempfile.NamedTemporaryFile() as f:
        f.write(provenance.model_dump_json().encode("utf-8"))
        f.flush()

        storage.store(
            provenance_file_path,
            f.name,
        )

        file_digest = hashlib.file_digest(f, "sha256")

    return provenance_file_path, file_digest.hexdigest()
