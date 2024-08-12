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

import pretend
import pytest

from pypi_attestations import (
    Attestation,
    AttestationBundle,
    Envelope,
    GitHubPublisher,
    GitLabPublisher,
    Provenance,
    VerificationMaterial,
)

import warehouse.packaging

from tests.common.db.oidc import GitHubPublisherFactory, GitLabPublisherFactory
from tests.common.db.packaging import FileEventFactory, FileFactory
from warehouse.attestations._core import (
    generate_and_store_provenance_file,
    get_provenance_digest,
    publisher_from_oidc_publisher,
)
from warehouse.attestations.errors import UnknownPublisherError
from warehouse.events.tags import EventTag
from warehouse.packaging import IFileStorage


def test_get_provenance_digest(db_request):
    file = FileFactory.create()
    FileEventFactory.create(
        source=file,
        tag=EventTag.File.FileAdd,
        additional={"publisher_url": "fake-publisher-url"},
    )

    with tempfile.NamedTemporaryFile() as f:
        storage_service = pretend.stub(get=pretend.call_recorder(lambda p: f))

        db_request.find_service = pretend.call_recorder(
            lambda svc, name=None, context=None: {
                IFileStorage: storage_service,
            }.get(svc)
        )

        assert (
            get_provenance_digest(db_request, file)
            == hashlib.file_digest(f, "sha256").hexdigest()
        )


def test_get_provenance_digest_fails_no_publisher_url(db_request):
    file = FileFactory.create()

    # If the publisher_url is missing, there is no provenance file
    assert get_provenance_digest(db_request, file) is None


def test_get_provenance_digest_fails_no_attestations(db_request):
    # If the attestations are missing, there is no provenance file
    file = FileFactory.create()
    file.attestations = []
    FileEventFactory.create(
        source=file,
        tag=EventTag.File.FileAdd,
        additional={"publisher_url": "fake-publisher-url"},
    )
    assert get_provenance_digest(db_request, file) is None


def test_publisher_from_oidc_publisher_github(db_request):
    publisher = GitHubPublisherFactory.create()

    attestation_publisher = publisher_from_oidc_publisher(publisher)
    assert isinstance(attestation_publisher, GitHubPublisher)
    assert attestation_publisher.repository == publisher.repository
    assert attestation_publisher.workflow == publisher.workflow_filename
    assert attestation_publisher.environment == publisher.environment


def test_publisher_from_oidc_publisher_gitlab(db_request):
    publisher = GitLabPublisherFactory.create()

    attestation_publisher = publisher_from_oidc_publisher(publisher)
    assert isinstance(attestation_publisher, GitLabPublisher)
    assert attestation_publisher.repository == publisher.project_path
    assert attestation_publisher.environment == publisher.environment


def test_publisher_from_oidc_publisher_fails(db_request, monkeypatch):

    publisher = pretend.stub(publisher_name="not-existing")

    with pytest.raises(UnknownPublisherError):
        publisher_from_oidc_publisher(publisher)


def test_generate_and_store_provenance_file_no_publisher(db_request):
    db_request.find_service = pretend.call_recorder(
        lambda svc, name=None, context=None: None
    )
    db_request.oidc_publisher = pretend.stub(publisher_name="not-existing")

    assert (
        generate_and_store_provenance_file(db_request, pretend.stub(), pretend.stub())
        is None
    )


def test_generate_and_store_provenance_file(db_request, monkeypatch):

    attestation = Attestation(
        version=1,
        verification_material=VerificationMaterial(
            certificate="somebase64string", transparency_entries=[dict()]
        ),
        envelope=Envelope(
            statement="somebase64string",
            signature="somebase64string",
        ),
    )
    publisher = GitHubPublisher(
        repository="fake-repository",
        workflow="fake-workflow",
    )
    provenance = Provenance(
        attestation_bundles=[
            AttestationBundle(
                publisher=publisher,
                attestations=[attestation],
            )
        ]
    )

    @pretend.call_recorder
    def storage_service_store(path: Path, file_path, *_args, **_kwargs):
        expected = provenance.model_dump_json().encode("utf-8")
        with open(file_path, "rb") as fp:
            assert fp.read() == expected

        assert path.suffix == ".provenance"

    storage_service = pretend.stub(store=storage_service_store)
    db_request.find_service = pretend.call_recorder(
        lambda svc, name=None, context=None: {
            IFileStorage: storage_service,
        }.get(svc)
    )

    monkeypatch.setattr(
        warehouse.attestations._core,
        "publisher_from_oidc_publisher",
        lambda s: publisher,
    )

    assert (
        generate_and_store_provenance_file(
            db_request, FileFactory.create(), [attestation]
        )
        is None
    )
