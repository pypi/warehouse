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

import pretend
import pytest

from tests.common.db.accounts import UserFactory
from tests.common.db.oidc import PendingGitHubProviderFactory
from tests.common.db.packaging import ProjectFactory
from warehouse.events.tags import EventTag
from warehouse.macaroons import caveats
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.oidc import views
from warehouse.oidc.interfaces import IOIDCProviderService


@pytest.mark.parametrize(
    ("registry", "admin"), [(False, False), (False, True), (True, True)]
)
def test_mint_token_from_oidc_not_enabled(registry, admin):
    request = pretend.stub(
        response=pretend.stub(status=None),
        registry=pretend.stub(settings={"warehouse.oidc.enabled": registry}),
        flags=pretend.stub(enabled=lambda *a: admin),
    )

    response = views.mint_token_from_oidc(request)
    assert request.response.status == 422
    assert response == {
        "message": "Token request failed",
        "errors": [
            {"code": "not-enabled", "description": "OIDC functionality not enabled"}
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
def test_mint_token_from_oidc_invalid_payload(body):
    class Request:
        def __init__(self):
            self.response = pretend.stub(status=None)
            self.registry = pretend.stub(settings={"warehouse.oidc.enabled": True})
            self.flags = pretend.stub(enabled=lambda *a: False)

        @property
        def body(self):
            return json.dumps(body)

    req = Request()
    resp = views.mint_token_from_oidc(req)

    assert req.response.status == 422
    assert resp["message"] == "Token request failed"
    assert isinstance(resp["errors"], list)
    for err in resp["errors"]:
        assert isinstance(err, dict)
        assert err["code"] == "invalid-payload"
        assert isinstance(err["description"], str)


def test_mint_token_from_oidc_provider_verify_jwt_signature_fails():
    oidc_service = pretend.stub(
        verify_jwt_signature=pretend.call_recorder(lambda token: None),
    )
    request = pretend.stub(
        response=pretend.stub(status=None),
        body=json.dumps({"token": "faketoken"}),
        find_service=pretend.call_recorder(lambda cls, **kw: oidc_service),
        registry=pretend.stub(settings={"warehouse.oidc.enabled": True}),
        flags=pretend.stub(enabled=lambda *a: False),
    )

    response = views.mint_token_from_oidc(request)
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

    assert request.find_service.calls == [
        pretend.call(IOIDCProviderService, name="github")
    ]
    assert oidc_service.verify_jwt_signature.calls == [pretend.call("faketoken")]


def test_mint_token_from_oidc_provider_lookup_fails():
    claims = pretend.stub()
    oidc_service = pretend.stub(
        verify_jwt_signature=pretend.call_recorder(lambda token: claims),
        find_provider=pretend.call_recorder(lambda claims, **kw: None),
    )
    request = pretend.stub(
        response=pretend.stub(status=None),
        body=json.dumps({"token": "faketoken"}),
        find_service=pretend.call_recorder(lambda cls, **kw: oidc_service),
        registry=pretend.stub(settings={"warehouse.oidc.enabled": True}),
        flags=pretend.stub(enabled=lambda *a: False),
    )

    response = views.mint_token_from_oidc(request)
    assert request.response.status == 422
    assert response == {
        "message": "Token request failed",
        "errors": [
            {
                "code": "invalid-provider",
                "description": "valid token, but no corresponding provider",
            }
        ],
    }

    assert request.find_service.calls == [
        pretend.call(IOIDCProviderService, name="github")
    ]
    assert oidc_service.verify_jwt_signature.calls == [pretend.call("faketoken")]
    assert oidc_service.find_provider.calls == [
        pretend.call(claims, pending=True),
        pretend.call(claims, pending=False),
    ]


def test_mint_token_from_oidc_pending_provider_project_already_exists(db_request):
    project = ProjectFactory.create()
    pending_provider = PendingGitHubProviderFactory.create(project_name=project.name)

    db_request.registry.settings = {"warehouse.oidc.enabled": True}
    db_request.flags.enabled = lambda f: False
    db_request.body = json.dumps({"token": "faketoken"})

    claims = pretend.stub()
    oidc_service = pretend.stub(
        verify_jwt_signature=pretend.call_recorder(lambda token: claims),
        find_provider=pretend.call_recorder(
            lambda claims, pending=False: pending_provider
        ),
    )
    db_request.find_service = pretend.call_recorder(lambda *a, **kw: oidc_service)

    resp = views.mint_token_from_oidc(db_request)
    assert db_request.response.status_code == 422
    assert resp == {
        "message": "Token request failed",
        "errors": [
            {
                "code": "invalid-pending-provider",
                "description": "valid token, but project already exists",
            }
        ],
    }

    assert oidc_service.verify_jwt_signature.calls == [pretend.call("faketoken")]
    assert oidc_service.find_provider.calls == [pretend.call(claims, pending=True)]
    assert db_request.find_service.calls == [
        pretend.call(IOIDCProviderService, name="github")
    ]


def test_mint_token_from_oidc_pending_provider_ok(
    db_request,
):
    user = UserFactory.create()
    PendingGitHubProviderFactory.create(
        project_name="does-not-exist",
        added_by=user,
        repository_name="bar",
        repository_owner="foo",
        repository_owner_id="123",
        workflow_filename="example.yml",
    )

    db_request.registry.settings = {"warehouse.oidc.enabled": True}
    db_request.flags.enabled = lambda f: False
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

    resp = views.mint_token_from_oidc(db_request)
    assert resp["success"]
    assert resp["token"].startswith("pypi-")


def test_mint_token_from_pending_oidc_provider_invalidates_others(
    monkeypatch, db_request
):
    time = pretend.stub(time=pretend.call_recorder(lambda: 0))
    monkeypatch.setattr(views, "time", time)

    user = UserFactory.create()
    PendingGitHubProviderFactory.create(
        project_name="does-not-exist",
        added_by=user,
        repository_name="bar",
        repository_owner="foo",
        repository_owner_id="123",
        workflow_filename="example.yml",
    )

    # Create some other pending providers for the same nonexistent project,
    # each of which should be invalidated. Invalidations occur based on the
    # normalized project name.
    emailed_users = []
    for project_name in ["does_not_exist", "does-not-exist", "dOeS-NoT-ExISt"]:
        user = UserFactory.create()
        PendingGitHubProviderFactory.create(
            project_name=project_name,
            added_by=user,
        )
        emailed_users.append(user)

    send_pending_oidc_provider_invalidated_email = pretend.call_recorder(
        lambda *a, **kw: None
    )
    monkeypatch.setattr(
        views,
        "send_pending_oidc_provider_invalidated_email",
        send_pending_oidc_provider_invalidated_email,
    )

    db_request.registry.settings = {"warehouse.oidc.enabled": True}
    db_request.flags.enabled = lambda f: False
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

    resp = views.mint_token_from_oidc(db_request)
    assert resp["success"]
    assert resp["token"].startswith("pypi-")

    # We should have sent one invalidation email for each pending provider that
    # was invalidated by the minting operation.
    assert send_pending_oidc_provider_invalidated_email.calls == [
        pretend.call(db_request, emailed_users[0], project_name="does_not_exist"),
        pretend.call(db_request, emailed_users[1], project_name="does-not-exist"),
        pretend.call(db_request, emailed_users[2], project_name="dOeS-NoT-ExISt"),
    ]


def test_mint_token_from_oidc_no_pending_provider_ok(monkeypatch):
    time = pretend.stub(time=pretend.call_recorder(lambda: 0))
    monkeypatch.setattr(views, "time", time)

    project = pretend.stub(
        id="fakeprojectid",
        record_event=pretend.call_recorder(lambda **kw: None),
    )
    provider = pretend.stub(
        id="fakeproviderid",
        projects=[project],
        provider_name="fakeprovidername",
        provider_url="https://fake/url",
    )
    # NOTE: Can't set __str__ using pretend.stub()
    monkeypatch.setattr(provider.__class__, "__str__", lambda s: "fakespecifier")

    claims = pretend.stub()
    oidc_service = pretend.stub(
        verify_jwt_signature=pretend.call_recorder(lambda token: claims),
        find_provider=pretend.call_recorder(
            lambda claims, pending=False: provider if not pending else None
        ),
    )

    db_macaroon = pretend.stub(description="fakemacaroon")
    macaroon_service = pretend.stub(
        create_macaroon=pretend.call_recorder(
            lambda *a, **kw: ("raw-macaroon", db_macaroon)
        )
    )

    def find_service(iface, **kw):
        if iface == IOIDCProviderService:
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
        registry=pretend.stub(settings={"warehouse.oidc.enabled": True}),
        flags=pretend.stub(enabled=lambda *a: False),
    )

    response = views.mint_token_from_oidc(request)
    assert response == {
        "success": True,
        "token": "raw-macaroon",
    }

    assert oidc_service.verify_jwt_signature.calls == [pretend.call("faketoken")]
    assert oidc_service.find_provider.calls == [
        pretend.call(claims, pending=True),
        pretend.call(claims, pending=False),
    ]
    assert macaroon_service.create_macaroon.calls == [
        pretend.call(
            "fakedomain",
            "OpenID token: https://fake/url (0)",
            [
                caveats.OIDCProvider(oidc_provider_id="fakeproviderid"),
                caveats.ProjectID(project_ids=["fakeprojectid"]),
                caveats.Expiration(expires_at=900, not_before=0),
            ],
            oidc_provider_id="fakeproviderid",
        )
    ]
    assert project.record_event.calls == [
        pretend.call(
            tag=EventTag.Project.ShortLivedAPITokenAdded,
            ip_address="0.0.0.0",
            additional={
                "expires": 900,
                "provider_name": "fakeprovidername",
                "provider_url": "https://fake/url",
            },
        )
    ]
