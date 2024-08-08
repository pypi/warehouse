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

from pydantic import TypeAdapter
from pypi_attestations import Attestation, GitHubPublisher, GitLabPublisher, AttestationBundle, Provenance

from warehouse.oidc.models import OIDCPublisher
from warehouse.oidc.models import GitLabPublisher as GitLabOIDCPublisher
from warehouse.oidc.models import GitHubPublisher as GitHubOIDCPublisher


from warehouse.packaging import File, ISimpleStorage


if typing.TYPE_CHECKING:
    from pypi_attestations import Publisher


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


# def generate_provenance_file(
#     request, publisher_url: str, file: File
# ) -> tuple[Path, str]:
#
#     storage = request.find_service(ISimpleStorage)
#
#     if publisher_url.startswith("https://github.com/"):
#         publisher = GitHubPublisher()
#     elif publisher_url.startswith("https://gitlab.com"):
#         publisher = GitLabPublisher()
#     else:
#         raise Exception()  # TODO(dm)
#
#     attestation_bundle = AttestationBundle(
#         publisher=publisher,
#         attestations=[
#             TypeAdapter(Attestation).validate_json(
#                 Path(release_attestation.attestation_path).read_text()
#             )
#             for release_attestation in file.attestations
#         ],
#     )
#
#     provenance = Provenance(attestation_bundles=[attestation_bundle])
#
#     provenance_file_path = Path(f"{file.path}.provenance")
#     with tempfile.NamedTemporaryFile() as f:
#         f.write(provenance.model_dump_json().encode("utf-8"))
#         f.flush()
#
#         storage.store(
#             provenance_file_path,
#             f.name,
#         )
#
#         file_digest = hashlib.file_digest(f, "sha256")
#
#     return provenance_file_path, file_digest.hexdigest()


def publisher_from_oidc_publisher(publisher: OIDCPublisher) -> Publisher:
    match publisher.publisher_name:
        case "GitLab":
            publisher = typing.cast(publisher, GitLabOIDCPublisher)
            return GitLabPublisher(repository=publisher.project_path, environment="")  # TODO(dm)
        case "GitHub":
            publisher = typing.cast(publisher, GitHubOIDCPublisher)
            return GitHubPublisher(repository=publisher.repository, workflow="", environment="")
        case _:
            raise Exception()  # TODO(dm)


def generate_provenance_file2(request, file: File, oidc_publisher: OIDCPublisher, oidc_claims, attestations: list[Attestation]):
    storage = request.find_service(ISimpleStorage)

    # First
    publisher: Publisher = publisher_from_oidc_publisher(oidc_publisher)

    attestation_bundle = AttestationBundle(
        publisher=publisher,
        attestations=[
            TypeAdapter(Attestation).validate_json(
                Path(release_attestation.attestation_path).read_text()
            )
            for release_attestation in file.attestations
        ],
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

        file_digest = hashlib.file_digest(f, "sha256")
    pass
