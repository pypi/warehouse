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

import base64
import hashlib

from http import HTTPStatus
from pathlib import Path

import pymacaroons

from warehouse.macaroons import caveats

from ...common.db.accounts import EmailFactory, UserFactory
from ...common.db.macaroons import MacaroonFactory
from ...common.db.oidc import GitHubPublisherFactory
from ...common.db.packaging import ProjectFactory, ReleaseFactory, RoleFactory

_HERE = Path(__file__).parent
_ASSETS = _HERE.parent / "_fixtures"


def test_simple_api_html(webtest):
    resp = webtest.get("/simple/", status=HTTPStatus.OK)

    assert resp.content_type == "text/html"
    assert "X-PyPI-Last-Serial" in resp.headers


def test_simple_api_detail(webtest):
    project = ProjectFactory.create()
    ReleaseFactory.create_batch(2, project=project)

    resp = webtest.get(f"/simple/{project.normalized_name}/", status=HTTPStatus.OK)

    assert resp.content_type == "text/html"
    assert "X-PyPI-Last-Serial" in resp.headers
    assert f"Links for {project.normalized_name}" in resp.text


def test_simple_attestations_from_upload(webtest):
    user = UserFactory.create(
        password=(  # 'password'
            "$argon2id$v=19$m=1024,t=6,p=6$EiLE2Nsbo9S6N+acs/beGw$ccyZDCZstr1/+Y/1s3BVZ"
            "HOJaqfBroT0JCieHug281c"
        )
    )
    EmailFactory.create(user=user, verified=True)
    project = ProjectFactory.create(name="sampleproject")
    RoleFactory.create(user=user, project=project, role_name="Owner")
    publisher = GitHubPublisherFactory.create(projects=[project])

    # Construct the macaroon. This needs to be based on a Trusted Publisher, which is
    # required to upload attestations
    dm = MacaroonFactory.create(
        oidc_publisher_id=publisher.id,
        caveats=[
            caveats.OIDCPublisher(oidc_publisher_id=str(publisher.id)),
            caveats.ProjectID(project_ids=[str(p.id) for p in publisher.projects]),
        ],
        additional={"oidc": {"ref": "someref", "sha": "somesha"}},
    )

    m = pymacaroons.Macaroon(
        location="localhost",
        identifier=str(dm.id),
        key=dm.key,
        version=pymacaroons.MACAROON_V2,
    )
    for caveat in dm.caveats:
        m.add_first_party_caveat(caveats.serialize(caveat))
    serialized_macaroon = f"pypi-{m.serialize()}"

    credentials = base64.b64encode(f"__token__:{serialized_macaroon}".encode()).decode(
        "utf-8"
    )

    with open(_ASSETS / "sampleproject-3.0.0.tar.gz", "rb") as f:
        content = f.read()

    with open(
        _ASSETS / "sampleproject-3.0.0.tar.gz.publish.attestation",
    ) as f:
        attestation = f.read()

    expected_hash = hashlib.sha256(
        # Filename:len(attestations)
        b"sampleproject-3.0.0.tar.gz:1"
    ).hexdigest()

    webtest.post(
        "/legacy/?:action=file_upload",
        headers={"Authorization": f"Basic {credentials}"},
        params={
            "name": "sampleproject",
            "sha256_digest": (
                "117ed88e5db073bb92969a7545745fd977ee85b7019706dd256a64058f70963d"
            ),
            "filetype": "sdist",
            "metadata_version": "2.1",
            "version": "3.0.0",
            "attestations": f"[{attestation}]",
        },
        upload_files=[("content", "sampleproject-3.0.0.tar.gz", content)],
        status=HTTPStatus.OK,
    )

    response = webtest.get("/simple/sampleproject/", status=HTTPStatus.OK)
    link = response.html.find("a", text="sampleproject-3.0.0.tar.gz")
    assert "data-provenance" in link.attrs
    assert link.get("data-provenance") == expected_hash
