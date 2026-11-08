# SPDX-License-Identifier: Apache-2.0

import base64

from http import HTTPStatus

import pytest

from tests.common.db import Session
from tests.common.db.accounts import UserFactory
from tests.common.db.packaging import ProjectFactory
from warehouse.macaroons import caveats
from warehouse.macaroons.services import DatabaseMacaroonService

DANGER_JSON = "application/vnd.pypi.api-v0-danger+json"


@pytest.fixture
def observer_token():
    observer = UserFactory.create(is_observer=True, clear_pwd="password")
    raw_token, _ = DatabaseMacaroonService(Session).create_macaroon(
        location="localhost",
        description="observations",
        scopes=[caveats.RequestUser(user_id=str(observer.id))],
        user_id=observer.id,
    )
    return raw_token


def _authorization(scheme, token):
    if scheme == "Basic":
        return "Basic " + base64.b64encode(f"__token__:{token}".encode()).decode()
    return f"{scheme} {token}"


@pytest.mark.parametrize("scheme", ["Bearer", "token", "Basic"])
def test_echo(webtest, observer_token, scheme):
    """Each scheme the macaroon policy accepts passes OpenAPI validation."""
    resp = webtest.get(
        "/danger-api/echo",
        headers={
            "Authorization": _authorization(scheme, observer_token),
            "Accept": DANGER_JSON,
        },
        status=HTTPStatus.OK,
    )

    assert "username" in resp.json


@pytest.mark.parametrize("scheme", ["Bearer", "token", "Basic"])
def test_observation(webtest, observer_token, scheme):
    project = ProjectFactory.create()

    webtest.post_json(
        f"/danger-api/projects/{project.name}/observations",
        {"kind": "is_spam", "summary": "spam"},
        headers={
            "Authorization": _authorization(scheme, observer_token),
            "Accept": DANGER_JSON,
            "Content-Type": DANGER_JSON,
        },
        status=HTTPStatus.ACCEPTED,
    )
