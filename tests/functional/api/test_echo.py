# SPDX-License-Identifier: Apache-2.0

import base64

from http import HTTPStatus

import pytest

from tests.common.db import Session
from tests.common.db.accounts import UserFactory
from tests.common.db.packaging import ProjectFactory
from warehouse.db import DatabaseNotAvailableError
from warehouse.macaroons import caveats
from warehouse.macaroons.services import DatabaseMacaroonService
from warehouse.packaging.models import Project

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


@pytest.fixture
def observer_headers(observer_token):
    return {
        "Authorization": f"Bearer {observer_token}",
        "Accept": DANGER_JSON,
        "Content-Type": DANGER_JSON,
    }


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


def test_observation_fails_validation(webtest, observer_headers):
    """Our problem details view wins over pyramid_openapi3's own."""
    project = ProjectFactory.create()

    resp = webtest.post_json(
        f"/danger-api/projects/{project.name}/observations",
        {"kind": "is_spam"},
        headers=observer_headers,
        status=HTTPStatus.BAD_REQUEST,
    )

    assert resp.content_type == "application/problem+json"
    assert resp.json["detail"] == "The request failed validation."
    assert resp.json["errors"]


def test_malware_observation_needs_inspector_url(webtest, observer_headers):
    project = ProjectFactory.create()

    resp = webtest.post_json(
        f"/danger-api/projects/{project.name}/observations",
        {"kind": "is_malware", "summary": "bad"},
        headers=observer_headers,
        status=HTTPStatus.BAD_REQUEST,
    )

    assert resp.content_type == "application/problem+json"
    assert resp.json["missing"] == ["inspector_url"]


def test_unknown_project(webtest, observer_headers):
    resp = webtest.post_json(
        "/danger-api/projects/no-such-project/observations",
        {"kind": "is_spam", "summary": "spam"},
        headers=observer_headers,
        status=HTTPStatus.NOT_FOUND,
    )

    assert resp.content_type == "application/problem+json"


def test_error_inside_view(webtest, observer_headers, mocker):
    """An error the spec doesn't list passes response validation."""
    project = ProjectFactory.create()
    mocker.patch.object(
        Project, "record_observation", side_effect=DatabaseNotAvailableError
    )

    resp = webtest.post_json(
        f"/danger-api/projects/{project.name}/observations",
        {"kind": "is_spam", "summary": "spam"},
        headers=observer_headers,
        status=HTTPStatus.SERVICE_UNAVAILABLE,
    )

    assert resp.content_type == "application/problem+json"


def test_legacy_action_param(webtest):
    """The legacy API's forbidden view doesn't take over API paths."""
    resp = webtest.get(
        "/danger-api/echo?:action=x",
        headers={"Accept": DANGER_JSON},
        status=HTTPStatus.FORBIDDEN,
    )

    assert resp.content_type == "application/problem+json"
    assert resp.json["detail"] == "Access was denied to this resource."
