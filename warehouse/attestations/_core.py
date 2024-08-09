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
import typing

from pathlib import Path

from pypi_attestations import (
    Attestation,
    AttestationBundle,
    GitHubPublisher,
    GitLabPublisher,
    Provenance,
    Publisher,
)

from warehouse.oidc.models import (
    GitHubPublisher as GitHubOIDCPublisher,
    GitLabPublisher as GitLabOIDCPublisher,
    OIDCPublisher,
)
from warehouse.packaging import File, ISimpleStorage


def get_provenance_digest(request, file: File) -> str | None:
    """Returns the sha256 digest of the provenance file for the release."""
    if not file.attestations or not file.publisher_url:
        return None

    storage = request.find_service(ISimpleStorage)
    provenance_file = storage.get(f"{file.path}.provenance")

    return hashlib.file_digest(provenance_file, "sha256").hexdigest()


def publisher_from_oidc_publisher(publisher: OIDCPublisher) -> Publisher:
    match publisher.publisher_name:
        case "GitLab":
            publisher = typing.cast(GitLabOIDCPublisher, publisher)
            return GitLabPublisher(
                repository=publisher.project_path, environment=""
            )  # TODO(dm)
        case "GitHub":
            publisher = typing.cast(GitHubOIDCPublisher, publisher)
            return GitHubPublisher(
                repository=publisher.repository, workflow="", environment=""
            )
        case _:
            raise Exception()  # TODO(dm)


def generate_and_store_provenance_file(
    request, file: File, attestations: list[Attestation]
):
    storage = request.find_service(ISimpleStorage)

    publisher: Publisher = publisher_from_oidc_publisher(request.oidc_publisher)

    attestation_bundle = AttestationBundle(
        publisher=publisher,
        attestations=attestations,
    )

    provenance = Provenance(attestation_bundles=[attestation_bundle])

    provenance_file_path = Path(f"{file.path}.provenance")
    with tempfile.NamedTemporaryFile() as f:
        f.write(provenance.model_dump_json().encode("utf-8"))
        f.flush()

        storage.store(
            provenance_file_path,
            f.name,
        )
