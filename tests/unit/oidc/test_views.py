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

from datetime import datetime

import pretend
import pytest

from tests.common.db.accounts import UserFactory
from tests.common.db.oidc import PendingGitHubPublisherFactory
from tests.common.db.packaging import ProjectFactory
from warehouse.events.tags import EventTag
from warehouse.macaroons import caveats
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.oidc import errors, views
from warehouse.oidc.interfaces import IOIDCPublisherService
from warehouse.oidc.models import github
from warehouse.packaging.models import Project
from warehouse.rate_limiting.interfaces import IRateLimiter


def test_ratelimiters():
    ratelimiter = pretend.stub()
    request = pretend.stub(
        find_service=pretend.call_recorder(lambda *a, **kw: ratelimiter)
    )

    assert views._ratelimiters(request) == {
        "user.oidc": ratelimiter,
        "ip.oidc": ratelimiter,
    }

    assert request.find_service.calls == [
        pretend.call(IRateLimiter, name="user_oidc.publisher.register"),
        pretend.call(IRateLimiter, name="ip_oidc.publisher.register"),
    ]


def test_oidc_audience_not_enabled():
    request = pretend.stub(
        flags=pretend.stub(disallow_oidc=lambda *a: True),
    )

    response = views.oidc_audience(request)
    assert response.status_code == 403
    assert response.json == {"message": "Trusted publishing functionality not enabled"}


def test_oidc_audience():
    request = pretend.stub(
        registry=pretend.stub(
            settings={
                "warehouse.oidc.audience": "fakeaudience",
            }
        ),
        flags=pretend.stub(disallow_oidc=lambda *a: False),
    )

    response = views.oidc_audience(request)
    assert response == {"audience": "fakeaudience"}


def test_mint_token_from_github_oidc_not_enabled():
    request = pretend.stub(
        response=pretend.stub(status=None),
        flags=pretend.stub(disallow_oidc=lambda *a: True),
    )

    response = views.mint_token_from_oidc_github(request)
    assert request.response.status == 422
    assert response == {
        "message": "Token request failed",
        "errors": [
            {
                "code": "not-enabled",
                "description": (
                    "GitHub-based trusted publishing functionality not enabled"
                ),
            }
        ],
    }


@pytest.mark.parametrize(
    "body",
    [
        "",
        [],
        "this is a valid JSON string",
        12345,
        3.14,
        None,
        {},
        {"token": None},
        {"wrongkey": ""},
        {"token": 3.14},
        {"token": 0},
        {"token": [""]},
        {"token": []},
        {"token": {}},
    ],
)
def test_mint_token_from_github_oidc_invalid_payload(body):
    class Request:
        def __init__(self):
            self.response = pretend.stub(status=None)
            self.flags = pretend.stub(disallow_oidc=lambda *a: False)

        @property
        def body(self):
            return json.dumps(body)

    req = Request()
    oidc_service = pretend.stub()
    resp = views.mint_token(oidc_service, req)

    assert req.response.status == 422
    assert resp["message"] == "Token request failed"
    assert isinstance(resp["errors"], list)
    for err in resp["errors"]:
        assert isinstance(err, dict)
        assert err["code"] == "invalid-payload"
        assert isinstance(err["description"], str)


def test_mint_token_from_trusted_publisher_verify_jwt_signature_fails():
    oidc_service = pretend.stub(
        verify_jwt_signature=pretend.call_recorder(lambda token: None),
    )
    request = pretend.stub(
        response=pretend.stub(status=None),
        body=json.dumps({"token": "faketoken"}),
        find_service=pretend.call_recorder(lambda cls, **kw: oidc_service),
        flags=pretend.stub(disallow_oidc=lambda *a: False),
    )

    response = views.mint_token(oidc_service, request)
    assert request.response.status == 422
    assert response == {
        "message": "Token request failed",
        "errors": [
            {
                "code": "invalid-token",
                "description": "malformed or invalid token",
            }
        ],
    }

    assert oidc_service.verify_jwt_signature.calls == [pretend.call("faketoken")]


def test_mint_token_from_trusted_publisher_lookup_fails():
    claims = pretend.stub()
    message = "some message"
    oidc_service = pretend.stub(
        verify_jwt_signature=pretend.call_recorder(lambda token: claims),
        find_publisher=pretend.call_recorder(
            pretend.raiser(errors.InvalidPublisherError(message))
        ),
    )
    request = pretend.stub(
        response=pretend.stub(status=None),
        body=json.dumps({"token": "faketoken"}),
        find_service=pretend.call_recorder(lambda cls, **kw: oidc_service),
        flags=pretend.stub(disallow_oidc=lambda *a: False),
    )

    response = views.mint_token_from_oidc_github(request)
    assert request.response.status == 422
    assert response == {
        "message": "Token request failed",
        "errors": [
            {
                "code": "invalid-publisher",
                "description": (
                    f"valid token, but no corresponding publisher ({message})"
                ),
            }
        ],
    }

    assert request.find_service.calls == [
        pretend.call(IOIDCPublisherService, name="github"),
    ]
    assert oidc_service.verify_jwt_signature.calls == [pretend.call("faketoken")]
    assert oidc_service.find_publisher.calls == [
        pretend.call(claims, pending=True),
        pretend.call(claims, pending=False),
    ]


def test_mint_token_from_oidc_pending_publisher_project_already_exists(db_request):
    project = ProjectFactory.create()
    pending_publisher = PendingGitHubPublisherFactory.create(project_name=project.name)

    db_request.flags.disallow_oidc = lambda f=None: False
    db_request.body = json.dumps({"token": "faketoken"})

    claims = pretend.stub()
    oidc_service = pretend.stub(
        verify_jwt_signature=pretend.call_recorder(lambda token: claims),
        find_publisher=pretend.call_recorder(
            lambda claims, pending=False: pending_publisher
        ),
    )
    db_request.find_service = pretend.call_recorder(lambda *a, **kw: oidc_service)

    resp = views.mint_token(oidc_service, db_request)
    assert db_request.response.status_code == 422
    assert resp == {
        "message": "Token request failed",
        "errors": [
            {
                "code": "invalid-pending-publisher",
                "description": "valid token, but project already exists",
            }
        ],
    }

    assert oidc_service.verify_jwt_signature.calls == [pretend.call("faketoken")]
    assert oidc_service.find_publisher.calls == [pretend.call(claims, pending=True)]


def test_mint_token_from_oidc_pending_publisher_ok(
    monkeypatch,
    db_request,
):
    user = UserFactory.create()
    pending_publisher = PendingGitHubPublisherFactory.create(
        project_name="does-not-exist",
        added_by=user,
        repository_name="bar",
        repository_owner="foo",
        repository_owner_id="123",
        workflow_filename="example.yml",
        environment="",
    )

    db_request.flags.disallow_oidc = lambda f=None: False
    db_request.body = json.dumps(
        {
            "token": (
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiI2ZTY3YjFjYi0yYjhkLTRi"
                "ZTUtOTFjYi03NTdlZGIyZWM5NzAiLCJzdWIiOiJyZXBvOmZvby9iYXIiLCJhdWQiOiJwe"
                "XBpIiwicmVmIjoiZmFrZSIsInNoYSI6ImZha2UiLCJyZXBvc2l0b3J5IjoiZm9vL2Jhci"
                "IsInJlcG9zaXRvcnlfb3duZXIiOiJmb28iLCJyZXBvc2l0b3J5X293bmVyX2lkIjoiMTI"
                "zIiwicnVuX2lkIjoiZmFrZSIsInJ1bl9udW1iZXIiOiJmYWtlIiwicnVuX2F0dGVtcHQi"
                "OiIxIiwicmVwb3NpdG9yeV9pZCI6ImZha2UiLCJhY3Rvcl9pZCI6ImZha2UiLCJhY3Rvc"
                "iI6ImZvbyIsIndvcmtmbG93IjoiZmFrZSIsImhlYWRfcmVmIjoiZmFrZSIsImJhc2Vfcm"
                "VmIjoiZmFrZSIsImV2ZW50X25hbWUiOiJmYWtlIiwicmVmX3R5cGUiOiJmYWtlIiwiZW5"
                "2aXJvbm1lbnQiOiJmYWtlIiwiam9iX3dvcmtmbG93X3JlZiI6ImZvby9iYXIvLmdpdGh1"
                "Yi93b3JrZmxvd3MvZXhhbXBsZS55bWxAZmFrZSIsImlzcyI6Imh0dHBzOi8vdG9rZW4uY"
                "WN0aW9ucy5naXRodWJ1c2VyY29udGVudC5jb20iLCJuYmYiOjE2NTA2NjMyNjUsImV4cC"
                "I6MTY1MDY2NDE2NSwiaWF0IjoxNjUwNjYzODY1fQ.f-FMv5FF5sdxAWeUilYDt9NoE7Et"
                "0vbdNhK32c2oC-E"
            )
        }
    )
    db_request.remote_addr = "0.0.0.0"

    ratelimiter = pretend.stub(clear=pretend.call_recorder(lambda id: None))
    ratelimiters = {
        "user.oidc": ratelimiter,
        "ip.oidc": ratelimiter,
    }
    monkeypatch.setattr(views, "_ratelimiters", lambda r: ratelimiters)

    resp = views.mint_token_from_oidc_github(db_request)
    assert resp["success"]
    assert resp["token"].startswith("pypi-")

    assert ratelimiter.clear.calls == [
        pretend.call(pending_publisher.added_by.id),
        pretend.call(db_request.remote_addr),
    ]


def test_mint_token_from_pending_trusted_publisher_invalidates_others(
    monkeypatch, db_request
):
    time = pretend.stub(time=pretend.call_recorder(lambda: 0))
    monkeypatch.setattr(views, "time", time)

    user = UserFactory.create()
    pending_publisher = PendingGitHubPublisherFactory.create(
        project_name="does-not-exist",
        added_by=user,
        repository_name="bar",
        repository_owner="foo",
        repository_owner_id="123",
        workflow_filename="example.yml",
        environment="",
    )

    # Create some other pending publishers for the same nonexistent project,
    # each of which should be invalidated. Invalidations occur based on the
    # normalized project name.
    emailed_users = []
    for project_name in ["does_not_exist", "does-not-exist", "dOeS-NoT-ExISt"]:
        user = UserFactory.create()
        PendingGitHubPublisherFactory.create(
            project_name=project_name,
            added_by=user,
        )
        emailed_users.append(user)

    send_pending_trusted_publisher_invalidated_email = pretend.call_recorder(
        lambda *a, **kw: None
    )
    monkeypatch.setattr(
        views,
        "send_pending_trusted_publisher_invalidated_email",
        send_pending_trusted_publisher_invalidated_email,
    )

    db_request.flags.oidc_enabled = lambda f: False
    token = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiI2ZTY3YjFjYi0yYjhkLTRi"
        "ZTUtOTFjYi03NTdlZGIyZWM5NzAiLCJzdWIiOiJyZXBvOmZvby9iYXIiLCJhdWQiOiJwe"
        "XBpIiwicmVmIjoiZmFrZSIsInNoYSI6ImZha2UiLCJyZXBvc2l0b3J5IjoiZm9vL2Jhci"
        "IsInJlcG9zaXRvcnlfb3duZXIiOiJmb28iLCJyZXBvc2l0b3J5X293bmVyX2lkIjoiMTI"
        "zIiwicnVuX2lkIjoiZmFrZSIsInJ1bl9udW1iZXIiOiJmYWtlIiwicnVuX2F0dGVtcHQi"
        "OiIxIiwicmVwb3NpdG9yeV9pZCI6ImZha2UiLCJhY3Rvcl9pZCI6ImZha2UiLCJhY3Rvc"
        "iI6ImZvbyIsIndvcmtmbG93IjoiZmFrZSIsImhlYWRfcmVmIjoiZmFrZSIsImJhc2Vfcm"
        "VmIjoiZmFrZSIsImV2ZW50X25hbWUiOiJmYWtlIiwicmVmX3R5cGUiOiJmYWtlIiwiZW5"
        "2aXJvbm1lbnQiOiJmYWtlIiwiam9iX3dvcmtmbG93X3JlZiI6ImZvby9iYXIvLmdpdGh1"
        "Yi93b3JrZmxvd3MvZXhhbXBsZS55bWxAZmFrZSIsImlzcyI6Imh0dHBzOi8vdG9rZW4uY"
        "WN0aW9ucy5naXRodWJ1c2VyY29udGVudC5jb20iLCJuYmYiOjE2NTA2NjMyNjUsImV4cC"
        "I6MTY1MDY2NDE2NSwiaWF0IjoxNjUwNjYzODY1fQ.f-FMv5FF5sdxAWeUilYDt9NoE7Et"
        "0vbdNhK32c2oC-E"
    )
    db_request.body = json.dumps({"token": token})
    db_request.remote_addr = "0.0.0.0"

    ratelimiter = pretend.stub(clear=pretend.call_recorder(lambda id: None))
    ratelimiters = {
        "user.oidc": ratelimiter,
        "ip.oidc": ratelimiter,
    }
    monkeypatch.setattr(views, "_ratelimiters", lambda r: ratelimiters)

    oidc_service = db_request.find_service(IOIDCPublisherService, name="github")

    resp = views.mint_token(oidc_service, db_request)
    assert resp["success"]
    assert resp["token"].startswith("pypi-")

    # We should have sent one invalidation email for each pending publisher that
    # was invalidated by the minting operation.
    assert send_pending_trusted_publisher_invalidated_email.calls == [
        pretend.call(db_request, emailed_users[0], project_name="does_not_exist"),
        pretend.call(db_request, emailed_users[1], project_name="does-not-exist"),
        pretend.call(db_request, emailed_users[2], project_name="dOeS-NoT-ExISt"),
    ]

    assert ratelimiter.clear.calls == [
        pretend.call(pending_publisher.added_by.id),
        pretend.call(db_request.remote_addr),
    ]


@pytest.mark.parametrize(
    ("claims_in_token", "claims_input"),
    [
        ({"ref": "someref", "sha": "somesha"}, {"ref": "someref", "sha": "somesha"}),
        ({"ref": "someref"}, {"ref": "someref", "sha": None}),
        ({"sha": "somesha"}, {"ref": None, "sha": "somesha"}),
    ],
)
def test_mint_token_from_oidc_no_pending_publisher_ok(
    monkeypatch, claims_in_token, claims_input
):
    time = pretend.stub(time=pretend.call_recorder(lambda: 0))
    monkeypatch.setattr(views, "time", time)

    project = Project(id="fakeprojectid")
    monkeypatch.setattr(
        project, "record_event", pretend.call_recorder(lambda **kw: None)
    )

    publisher = github.GitHubPublisher(
        repository_name="fakerepo",
        repository_owner="fakeowner",
        repository_owner_id="fakeid",
        workflow_filename="fakeworkflow.yml",
        environment="fakeenv",
    )
    publisher.projects = [project]
    # NOTE: Can't set __str__ using pretend.stub()
    monkeypatch.setattr(publisher, "id", "fakepublisherid")

    def _find_publisher(claims, pending=False):
        if pending:
            raise errors.InvalidPublisherError
        else:
            return publisher

    oidc_service = pretend.stub(
        verify_jwt_signature=pretend.call_recorder(lambda token: claims_in_token),
        find_publisher=pretend.call_recorder(_find_publisher),
    )

    db_macaroon = pretend.stub(description="fakemacaroon")
    macaroon_service = pretend.stub(
        create_macaroon=pretend.call_recorder(
            lambda *a, **kw: ("raw-macaroon", db_macaroon)
        )
    )

    def find_service(iface, **kw):
        if iface == IOIDCPublisherService:
            return oidc_service
        elif iface == IMacaroonService:
            return macaroon_service
        assert False, iface

    request = pretend.stub(
        response=pretend.stub(status=None),
        body=json.dumps({"token": "faketoken"}),
        find_service=find_service,
        domain="fakedomain",
        remote_addr="0.0.0.0",
        flags=pretend.stub(disallow_oidc=lambda *a: False),
    )

    response = views.mint_token(oidc_service, request)
    assert response == {
        "success": True,
        "token": "raw-macaroon",
    }

    assert oidc_service.verify_jwt_signature.calls == [pretend.call("faketoken")]
    assert oidc_service.find_publisher.calls == [
        pretend.call(claims_in_token, pending=True),
        pretend.call(claims_in_token, pending=False),
    ]
    assert macaroon_service.create_macaroon.calls == [
        pretend.call(
            "fakedomain",
            f"OpenID token: fakeworkflow.yml ({datetime.fromtimestamp(0).isoformat()})",
            [
                caveats.OIDCPublisher(
                    oidc_publisher_id="fakepublisherid",
                ),
                caveats.ProjectID(project_ids=["fakeprojectid"]),
                caveats.Expiration(expires_at=900, not_before=0),
            ],
            oidc_publisher_id="fakepublisherid",
            additional={"oidc": claims_input},
        )
    ]
    assert project.record_event.calls == [
        pretend.call(
            tag=EventTag.Project.ShortLivedAPITokenAdded,
            request=request,
            additional={
                "expires": 900,
                "publisher_name": "GitHub",
                "publisher_url": f"https://github.com/{publisher.repository_owner}/{publisher.repository_name}",  # noqa
            },
        )
    ]
