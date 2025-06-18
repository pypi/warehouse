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
import json

from http import HTTPStatus
from pathlib import Path

import pymacaroons
import pytest

from webob.multidict import MultiDict

from tests.common.db.oidc import (
    ActiveStatePublisherFactory,
    GitHubPublisherFactory,
    GitLabPublisherFactory,
    GooglePublisherFactory,
)
from tests.common.db.packaging import ProjectFactory, RoleFactory
from warehouse.macaroons import caveats

from ...common.constants import (
    DUMMY_ACTIVESTATE_OIDC_JWT,
    DUMMY_GITHUB_OIDC_JWT,
    DUMMY_GITLAB_OIDC_JWT,
    DUMMY_GOOGLE_OIDC_JWT,
)
from ...common.db.accounts import UserFactory
from ...common.db.macaroons import MacaroonFactory

_HERE = Path(__file__).parent
_ASSETS = _HERE.parent / "_fixtures"
assert _ASSETS.is_dir()


def test_incorrect_post_redirect(webtest):
    """
    Per issue #8104, we should issue an HTTP-308 for a POST
    in /legacy and point the user to the correct endpoint,
    /legacy/

    See: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/308
    """
    resp = webtest.post("/legacy", status=HTTPStatus.PERMANENT_REDIRECT)
    assert resp.status == (
        "308 An upload was attempted to /legacy but the expected upload URL is "
        "/legacy/ (with a trailing slash)"
    )

    assert "location" in resp.headers
    assert resp.headers["location"] == "http://localhost/legacy/"


@pytest.mark.parametrize("action", ["submit", "submit_pkg_info"])
def test_removed_upload_apis(webtest, action):
    resp = webtest.post(f"/legacy/?:action={action}", status=HTTPStatus.GONE)
    assert resp.status == (
        "410 Project pre-registration is no longer required or supported, "
        "upload your files instead."
    )


def test_remove_doc_upload(webtest):
    resp = webtest.post("/legacy/?:action=doc_upload", status=HTTPStatus.GONE)
    assert resp.status == (
        "410 Uploading documentation is no longer supported, we recommend "
        "using https://readthedocs.org/."
    )


@pytest.mark.parametrize(
    ("upload_url", "additional_data"),
    [
        ("/legacy/?:action=file_upload", {}),
        ("/legacy/", {":action": "file_upload", "protocol_version": "1"}),
    ],
)
def test_file_upload(webtest, upload_url, additional_data):
    user = UserFactory.create(with_verified_primary_email=True, clear_pwd="password")

    # Construct the macaroon
    dm = MacaroonFactory.create(
        user_id=user.id,
        caveats=[caveats.RequestUser(user_id=str(user.id))],
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

    with open("./tests/functional/_fixtures/sampleproject-3.0.0.tar.gz", "rb") as f:
        content = f.read()

    params = MultiDict(
        {
            "name": "sampleproject",
            "sha256_digest": (
                "117ed88e5db073bb92969a7545745fd977ee85b7019706dd256a64058f70963d"
            ),
            "filetype": "sdist",
            "metadata_version": "2.1",
            "version": "3.0.0",
        }
    )
    params.update(additional_data)
    params.add("project-url", "https://example.com/foo")
    params.add("project-url", "https://example.com/bar")
    params.add("classifiers", "Programming Language :: Python :: 3.10")
    params.add("classifiers", "Programming Language :: Python :: 3.11")

    webtest.post(
        upload_url,
        headers={"Authorization": f"Basic {credentials}"},
        params=params,
        upload_files=[("content", "sampleproject-3.0.0.tar.gz", content)],
        status=HTTPStatus.OK,
    )

    assert user.projects
    assert len(user.projects) == 1
    project = user.projects[0]
    assert project.name == "sampleproject"
    assert project.releases
    assert len(project.releases) == 1
    release = project.releases[0]
    assert release.version == "3.0.0"


def test_duplicate_file_upload_error(webtest):
    user = UserFactory.create(with_verified_primary_email=True, clear_pwd="password")

    # Construct the macaroon
    dm = MacaroonFactory.create(
        user_id=user.id,
        caveats=[caveats.RequestUser(user_id=str(user.id))],
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

    with open("./tests/functional/_fixtures/sampleproject-3.0.0.tar.gz", "rb") as f:
        content = f.read()

    params = MultiDict(
        {
            ":action": "file_upload",
            "protocol_version": "1",
            "name": "sampleproject",
            "sha256_digest": (
                "117ed88e5db073bb92969a7545745fd977ee85b7019706dd256a64058f70963d"
            ),
            "filetype": "sdist",
            "metadata_version": "2.1",
            "version": "3.0.0",
        }
    )

    webtest.post(
        "/legacy/",
        headers={"Authorization": f"Basic {credentials}"},
        params=params,
        upload_files=[("content", "sampleproject-3.0.0.tar.gz", content)],
        status=HTTPStatus.OK,
    )

    assert user.projects
    assert len(user.projects) == 1
    project = user.projects[0]
    assert project.name == "sampleproject"
    assert project.releases
    assert len(project.releases) == 1
    release = project.releases[0]
    assert release.version == "3.0.0"

    # Add some duplicate keys to ensure that this doesn't result in a error due
    # to the duplicate key detector
    params.add("project-url", "https://example.com/foo")
    params.add("project-url", "https://example.com/bar")
    params.add("classifiers", "Programming Language :: Python :: 3.10")
    params.add("classifiers", "Programming Language :: Python :: 3.11")

    resp = webtest.post(
        "/legacy/",
        headers={"Authorization": f"Basic {credentials}"},
        params=params,
        upload_files=[("content", "sampleproject-3.0.1.tar.gz", content)],
        status=HTTPStatus.BAD_REQUEST,
    )
    assert "File already exists" in resp.body.decode()


def test_typo_check_name_upload_passes(webtest, monkeypatch):
    """
    Test not blocking the upload of a release with a typo in the project name,
    and emits a notification to the admins.
    """
    # TODO: Replace with a better way to generate corpus
    monkeypatch.setattr(
        "warehouse.packaging.typosnyper._TOP_PROJECT_NAMES",
        {"wutang", "requests"},
    )

    # Set up user, credentials
    user = UserFactory.create(with_verified_primary_email=True, clear_pwd="password")
    # Construct the macaroon
    dm = MacaroonFactory.create(
        user_id=user.id,
        caveats=[caveats.RequestUser(user_id=str(user.id))],
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

    # use a dummy file for the upload, the filename/metadata doesn't matter here
    with open("./tests/functional/_fixtures/sampleproject-3.0.0.tar.gz", "rb") as f:
        content = f.read()

    # Construct params and upload
    params = MultiDict(
        {
            ":action": "file_upload",
            "protocol_version": "1",
            "name": "wutamg",  # Here is the typo
            "sha256_digest": (
                "117ed88e5db073bb92969a7545745fd977ee85b7019706dd256a64058f70963d"
            ),
            "filetype": "sdist",
            "metadata_version": "2.1",
            "version": "3.0.0",
        }
    )
    webtest.post(
        "/legacy/",
        headers={"Authorization": f"Basic {credentials}"},
        params=params,
        upload_files=[("content", "wutamg-3.0.0.tar.gz", content)],  # and here
        status=HTTPStatus.OK,
    )

    assert user.projects
    assert len(user.projects) == 1
    project = user.projects[0]
    assert project.name == "wutamg"  # confirming it passed
    assert project.releases
    assert len(project.releases) == 1
    release = project.releases[0]
    assert release.version == "3.0.0"


def test_invalid_classifier_upload_error(webtest):
    user = UserFactory.create(with_verified_primary_email=True, clear_pwd="password")

    # Construct the macaroon
    dm = MacaroonFactory.create(
        user_id=user.id,
        caveats=[caveats.RequestUser(user_id=str(user.id))],
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

    with open("./tests/functional/_fixtures/sampleproject-3.0.0.tar.gz", "rb") as f:
        content = f.read()

    params = MultiDict(
        {
            ":action": "file_upload",
            "protocol_version": "1",
            "name": "sampleproject",
            "sha256_digest": (
                "117ed88e5db073bb92969a7545745fd977ee85b7019706dd256a64058f70963d"
            ),
            "filetype": "sdist",
            "metadata_version": "2.1",
            "version": "3.0.0",
        }
    )
    params.add("classifiers", "Programming Language :: Python :: 3.10")
    params.add("classifiers", "This :: Is :: Invalid")

    resp = webtest.post(
        "/legacy/",
        headers={"Authorization": f"Basic {credentials}"},
        params=params,
        upload_files=[("content", "sampleproject-3.0.1.tar.gz", content)],
        status=HTTPStatus.BAD_REQUEST,
    )
    assert "'This :: Is :: Invalid' is not a valid classifier" in resp.body.decode()


def test_provenance_upload(webtest):
    user = UserFactory.create(with_verified_primary_email=True, clear_pwd="password")
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

    with open(_ASSETS / "sampleproject-3.0.0.tar.gz", "rb") as f:
        content = f.read()

    with open(
        _ASSETS / "sampleproject-3.0.0.tar.gz.publish.attestation",
    ) as f:
        attestation_contents = f.read()

    webtest.set_authorization(("Basic", ("__token__", serialized_macaroon)))
    webtest.post(
        "/legacy/?:action=file_upload",
        params={
            "name": "sampleproject",
            "sha256_digest": (
                "117ed88e5db073bb92969a7545745fd977ee85b7019706dd256a64058f70963d"
            ),
            "filetype": "sdist",
            "metadata_version": "2.1",
            "version": "3.0.0",
            "attestations": f"[{attestation_contents}]",
        },
        upload_files=[("content", "sampleproject-3.0.0.tar.gz", content)],
        status=HTTPStatus.OK,
    )

    assert len(project.releases) == 1
    release = project.releases[0]
    assert release.files.count() == 1
    file_ = project.releases[0].files[0]
    assert file_.provenance is not None
    provenance = file_.provenance.provenance
    assert "attestation_bundles" in provenance
    attestation_bundles = provenance["attestation_bundles"]
    assert len(attestation_bundles) == 1
    bundle = provenance["attestation_bundles"][0]
    assert "attestations" in bundle
    attestations = bundle["attestations"]
    assert len(attestations) == 1
    attestation = attestations[0]
    assert attestation == json.loads(attestation_contents)

    # While we needed to be authenticated to upload a project, this is no longer
    # required to view it.
    webtest.authorization = None
    expected_filename = "sampleproject-3.0.0.tar.gz"

    response = webtest.get(
        f"/integrity/{project.name}/3.0.0/{expected_filename}/provenance",
        status=HTTPStatus.OK,
    )
    assert response.json == project.releases[0].files[0].provenance.provenance


@pytest.mark.parametrize(
    ("publisher_factory", "publisher_data", "oidc_jwt"),
    [
        (
            GitHubPublisherFactory,
            {
                "repository_name": "bar",
                "repository_owner": "foo",
                "repository_owner_id": "123",
                "workflow_filename": "example.yml",
                "environment": "fake",
            },
            DUMMY_GITHUB_OIDC_JWT,
        ),
        (
            ActiveStatePublisherFactory,
            {
                "organization": "fakeorg",
                "activestate_project_name": "fakeproject",
                "actor": "foo",
                "actor_id": "fake",
            },
            DUMMY_ACTIVESTATE_OIDC_JWT,
        ),
        (
            GitLabPublisherFactory,
            {
                "namespace": "foo",
                "project": "bar",
                "workflow_filepath": ".gitlab-ci.yml",
                "environment": "",
            },
            DUMMY_GITLAB_OIDC_JWT,
        ),
        (
            GooglePublisherFactory,
            {
                "email": "user@example.com",
                "sub": "111260650121185072906",
            },
            DUMMY_GOOGLE_OIDC_JWT,
        ),
    ],
)
@pytest.mark.usefixtures("_enable_all_oidc_providers")
def test_trusted_publisher_upload_ok(
    webtest, publisher_factory, publisher_data, oidc_jwt
):
    user = UserFactory.create(with_verified_primary_email=True, clear_pwd="password")
    project = ProjectFactory.create(name="sampleproject")
    RoleFactory.create(user=user, project=project, role_name="Owner")
    publisher_factory.create(
        projects=[project],
        **publisher_data,
    )

    response = webtest.post_json(
        "/_/oidc/mint-token",
        params={
            "token": oidc_jwt,
        },
        status=HTTPStatus.OK,
    )

    assert "success" in response.json
    assert response.json["success"]
    assert "token" in response.json
    pypi_token = response.json["token"]
    assert pypi_token.startswith("pypi-")

    with open(_ASSETS / "sampleproject-3.0.0.tar.gz", "rb") as f:
        content = f.read()

    webtest.set_authorization(("Basic", ("__token__", pypi_token)))
    webtest.post(
        "/legacy/?:action=file_upload",
        params={
            "name": "sampleproject",
            "sha256_digest": (
                "117ed88e5db073bb92969a7545745fd977ee85b7019706dd256a64058f70963d"
            ),
            "filetype": "sdist",
            "metadata_version": "2.1",
            "version": "3.0.0",
        },
        upload_files=[("content", "sampleproject-3.0.0.tar.gz", content)],
        status=HTTPStatus.OK,
    )

    assert len(project.releases) == 1
    release = project.releases[0]
    assert release.files.count() == 1


@pytest.mark.parametrize(
    ("publisher_factory", "publisher_data", "oidc_jwt"),
    [
        (
            GitHubPublisherFactory,
            {
                "repository_name": "wrong",
                "repository_owner": "foo",
                "repository_owner_id": "123",
                "workflow_filename": "example.yml",
                "environment": "fake",
            },
            DUMMY_GITHUB_OIDC_JWT,
        ),
        (
            ActiveStatePublisherFactory,
            {
                "organization": "wrong",
                "activestate_project_name": "fakeproject",
                "actor": "foo",
                "actor_id": "fake",
            },
            DUMMY_ACTIVESTATE_OIDC_JWT,
        ),
        (
            GitLabPublisherFactory,
            {
                "namespace": "wrong",
                "project": "bar",
                "workflow_filepath": ".gitlab-ci.yml",
                "environment": "fake",
            },
            DUMMY_GITLAB_OIDC_JWT,
        ),
        (
            GooglePublisherFactory,
            {
                "email": "wrong@example.com",
                "sub": "111260650121185072906",
            },
            DUMMY_GOOGLE_OIDC_JWT,
        ),
    ],
)
@pytest.mark.usefixtures("_enable_all_oidc_providers")
def test_trusted_publisher_upload_fails_wrong_publisher(
    webtest, publisher_factory, publisher_data, oidc_jwt
):
    user = UserFactory.create(with_verified_primary_email=True, clear_pwd="password")
    project = ProjectFactory.create(name="sampleproject")
    RoleFactory.create(user=user, project=project, role_name="Owner")
    publisher_factory.create(
        projects=[project],
        **publisher_data,
    )
    response = webtest.post_json(
        "/_/oidc/mint-token",
        params={
            "token": oidc_jwt,
        },
        status=HTTPStatus.UNPROCESSABLE_CONTENT,
    )

    assert "token" not in response.json
    assert "message" in response.json
    assert response.json["message"] == "Token request failed"
    assert "errors" in response.json
    assert response.json["errors"] == [
        {
            "code": "invalid-publisher",
            "description": "valid token, but no corresponding publisher "
            "(Publisher with matching claims was not found)",
        }
    ]
