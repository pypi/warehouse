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

from http import HTTPStatus

import pymacaroons
import pytest

from warehouse.macaroons import caveats

from ...common.db.accounts import UserFactory
from ...common.db.macaroons import MacaroonFactory
from ...common.db.packaging import ProjectFactory, ReleaseFactory, RoleFactory


def _make_credentials(user):
    # Construct the macaroon.
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

    return base64.b64encode(f"__token__:{serialized_macaroon}".encode()).decode("utf-8")


def test_release_get(webtest):
    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)

    resp = webtest.get(
        f"/api/projects/{project.normalized_name}/{release.version}",
        headers={"Content-Type": "application/json"},
        status=HTTPStatus.OK,
    )
    assert resp.content_type == "application/json"
    info = resp.json["info"]
    assert not info["yanked"]
    assert info["yanked_reason"] is None


@pytest.mark.parametrize(
    "body",
    [{"yanked": True}, {"yanked": True, "yanked_reason": "because"}, {"yanked": False}],
)
def test_release_patch_noargs_unauthenticated(webtest, body):
    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)

    webtest.patch_json(
        f"/api/projects/{project.normalized_name}/{release.version}",
        params=body,
        status=HTTPStatus.FORBIDDEN,
    )


def test_release_patch_bad_payload(webtest):
    user = UserFactory.create(with_verified_primary_email=True, clear_pwd="password")
    credentials = _make_credentials(user)

    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)
    RoleFactory.create(user=user, project=project, role_name="Owner")

    webtest.patch(
        f"/api/projects/{project.normalized_name}/{release.version}",
        headers={"Authorization": f"Basic {credentials}"},
        params="xyz",
        status=HTTPStatus.BAD_REQUEST,
    )


def test_release_patch_no_payload(webtest):
    # 2024-10-17(warsaw): This test is here to mimic a body-less curl command such as:
    #
    # curl -X PATCH http://localhost/api/projects/dstufft-testpkg/21.0 -H "..." -u "..."
    #
    # Note the lack of a -d to pass data to the PATCH command.  This ends up
    # with request.body being None rather than an empty dictionary which could
    # be JSON-decoded.  The semantics are the same -- there's nothing to PATCH
    # so nothing to do.  This test is here just to get to 100% coverage.
    user = UserFactory.create(with_verified_primary_email=True, clear_pwd="password")
    credentials = _make_credentials(user)

    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)
    RoleFactory.create(user=user, project=project, role_name="Owner")

    webtest.patch(
        f"/api/projects/{project.normalized_name}/{release.version}",
        headers={"Authorization": f"Basic {credentials}"},
        status=HTTPStatus.OK,
    )


@pytest.mark.parametrize(
    ("role", "status"),
    [
        ("Owner", HTTPStatus.OK),
        ("Maintainer", HTTPStatus.FORBIDDEN),
    ],
)
def test_release_patch_single_by_role(webtest, role, status):
    user = UserFactory.create(with_verified_primary_email=True, clear_pwd="password")
    credentials = _make_credentials(user)

    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)
    RoleFactory.create(user=user, project=project, role_name=role)

    webtest.patch_json(
        f"/api/projects/{project.normalized_name}/{release.version}",
        headers={"Authorization": f"Basic {credentials}"},
        params={},
        status=status,
    )


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({}, {"yanked": False, "yanked_reason": None}),
        ({"yanked": True, "yanked_reason": "because"}, None),
        ({"yanked": True, "yanked_reason": None}, None),
        (
            {"yanked": False, "yanked_reason": "because"},
            {"yanked": False, "yanked_reason": None},
        ),
        ({"yanked": True}, {"yanked": True, "yanked_reason": None}),
        ({"yanked": False}, {"yanked": False, "yanked_reason": None}),
        ({"yanked_reason": "because"}, {"yanked": False, "yanked_reason": None}),
        ({"yanked": "not-a-bool", "yanked_reason": "because"}, HTTPStatus.BAD_REQUEST),
        ({"yanked": True, "yanked_reason": 7}, HTTPStatus.BAD_REQUEST),
    ],
)
def test_release_patch_single(webtest, body, expected):
    user = UserFactory.create(with_verified_primary_email=True, clear_pwd="password")
    credentials = _make_credentials(user)

    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)
    RoleFactory.create(user=user, project=project, role_name="Owner")

    status = HTTPStatus.OK
    if expected is None:
        expected = body
    elif isinstance(expected, HTTPStatus):
        status = expected

    resp = webtest.patch_json(
        f"/api/projects/{project.normalized_name}/{release.version}",
        headers={"Authorization": f"Basic {credentials}"},
        params=body,
        status=status,
    )

    if status != HTTPStatus.OK:
        return

    info = resp.json["info"]

    for key, value in expected.items():
        assert info[key] == value


def test_release_transitions(webtest):
    user = UserFactory.create(with_verified_primary_email=True, clear_pwd="password")
    credentials = _make_credentials(user)

    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)
    RoleFactory.create(user=user, project=project, role_name="Owner")

    # Start by yanking a release with a reason.
    resp = webtest.patch_json(
        f"/api/projects/{project.normalized_name}/{release.version}",
        headers={"Authorization": f"Basic {credentials}"},
        params={"yanked": True, "yanked_reason": "because"},
        status=HTTPStatus.OK,
    )

    info = resp.json["info"]
    assert info["yanked"]
    assert info["yanked_reason"] == "because"

    # Yanking again without a reason does not change the previous reason.
    resp = webtest.patch_json(
        f"/api/projects/{project.normalized_name}/{release.version}",
        headers={"Authorization": f"Basic {credentials}"},
        params={"yanked": True},
        status=HTTPStatus.OK,
    )

    info = resp.json["info"]
    assert info["yanked"]
    assert info["yanked_reason"] == "because"

    # The package is still yanked, so you can change the reason.
    resp = webtest.patch_json(
        f"/api/projects/{project.normalized_name}/{release.version}",
        headers={"Authorization": f"Basic {credentials}"},
        params={"yanked_reason": "why not"},
        status=HTTPStatus.OK,
    )

    info = resp.json["info"]
    assert info["yanked"]
    assert info["yanked_reason"] == "why not"

    # Unyanking the package resets the reason.
    resp = webtest.patch_json(
        f"/api/projects/{project.normalized_name}/{release.version}",
        headers={"Authorization": f"Basic {credentials}"},
        params={"yanked": False},
        status=HTTPStatus.OK,
    )

    info = resp.json["info"]
    assert not info["yanked"]
    assert info["yanked_reason"] is None

    # Setting the reason for an unyanking package ignores the reason.
    resp = webtest.patch_json(
        f"/api/projects/{project.normalized_name}/{release.version}",
        headers={"Authorization": f"Basic {credentials}"},
        params={"yanked_reason": "unyanked"},
        status=HTTPStatus.OK,
    )

    info = resp.json["info"]
    assert not info["yanked"]
    assert info["yanked_reason"] is None
