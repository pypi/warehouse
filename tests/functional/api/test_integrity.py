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

import json

from http import HTTPStatus
from pathlib import Path

from ...common.db.packaging import (
    FileFactory,
    ProjectFactory,
    ProvenanceFactory,
    ReleaseFactory,
)

_HERE = Path(__file__).parent
_ASSETS = _HERE.parent / "_fixtures"
assert _ASSETS.is_dir()


def test_provenance_available(webtest):
    with open(
        _ASSETS / "sampleproject-3.0.0.tar.gz.publish.attestation",
    ) as f:
        attestation_contents = f.read()
        attestation_json = json.loads(attestation_contents)

    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)
    file_ = FileFactory.create(release=release, packagetype="sdist")
    ProvenanceFactory.create(
        file=file_,
        provenance={"attestation_bundles": [{"attestations": [attestation_json]}]},
    )

    response = webtest.get(
        f"/integrity/{project.name}/{release.version}/{file_.filename}/provenance",
        status=HTTPStatus.OK,
    )
    assert response.json
    assert "attestation_bundles" in response.json
    attestation_bundles = response.json["attestation_bundles"]
    assert len(attestation_bundles) == 1
    attestation_bundle = attestation_bundles[0]
    assert "attestations" in attestation_bundle
    attestations = attestation_bundle["attestations"]
    assert len(attestations) == 1
    attestation = attestations[0]
    assert attestation == attestation_json
