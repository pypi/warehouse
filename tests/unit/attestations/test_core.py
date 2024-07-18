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
import pathlib

from pathlib import Path

import pretend

from pypi_attestations import Attestation, Envelope, VerificationMaterial

import warehouse.packaging

from tests.common.db.packaging import FileFactory
from warehouse.attestations._core import generate_provenance_file, get_provenance_digest
from warehouse.events.tags import EventTag
from warehouse.packaging import ISimpleStorage

from ...common.db.packaging import FileEventFactory


def test_get_provenance_digest_succeed(db_request, monkeypatch):
    file = FileFactory.create()
    FileEventFactory.create(
        source=file,
        tag=EventTag.Project.ReleaseAdd,
        additional={"publisher_url": "fake-publisher-url"},
    )

    generate_provenance_file = pretend.call_recorder(
        lambda request, publisher_url, file_: (Path("fake-path"), "deadbeef")
    )
    monkeypatch.setattr(
        warehouse.attestations._core,
        "generate_provenance_file",
        generate_provenance_file,
    )

    hex_digest = get_provenance_digest(db_request, file)

    assert hex_digest == "deadbeef"


def test_get_provenance_digest_fails_no_attestations(db_request, monkeypatch):
    file = FileFactory.create()
    monkeypatch.setattr(warehouse.packaging.models.File, "attestations", [])

    provenance_hash = get_provenance_digest(db_request, file)
    assert provenance_hash is None


def test_get_provenance_digest_fails_no_publisher_url(db_request, monkeypatch):
    file = FileFactory.create()

    provenance_hash = get_provenance_digest(db_request, file)
    assert provenance_hash is None


def test_generate_provenance_file_succeed(db_request, monkeypatch):

    def store_function(path, file_path, *, meta=None):
        return f"https://files/attestations/{path}.provenance"

    storage_service = pretend.stub(store=pretend.call_recorder(store_function))

    db_request.find_service = pretend.call_recorder(
        lambda svc, name=None, context=None: {
            ISimpleStorage: storage_service,
        }.get(svc)
    )

    publisher_url = "x-fake-publisher-url"
    file = FileFactory.create()
    FileEventFactory.create(
        source=file,
        tag=EventTag.Project.ReleaseAdd,
        additional={"publisher_url": publisher_url},
    )

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

    read_text = pretend.call_recorder(lambda _: attestation.model_dump_json())

    monkeypatch.setattr(pathlib.Path, "read_text", read_text)

    provenance_file_path, provenance_hash = generate_provenance_file(
        db_request, publisher_url, file
    )

    assert provenance_hash is not None
