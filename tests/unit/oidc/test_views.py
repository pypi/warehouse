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

from urllib import request

import pretend
import pytest

from tests.common.db.oidc import GitHubProviderFactory, PendingGitHubProviderFactory
from tests.common.db.packaging import ProjectFactory
from warehouse import oidc
from warehouse.events.tags import EventTag
from warehouse.macaroons import caveats
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.oidc import views
from warehouse.oidc.interfaces import IOIDCProviderService
from warehouse.oidc.utils import reify_pending_provider


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


def test_mint_token_from_oidc_pending_provider_ok(monkeypatch, db_request):
    time = pretend.stub(time=pretend.call_recorder(lambda: 0))
    monkeypatch.setattr(views, "time", time)

    pending_provider = PendingGitHubProviderFactory.create(
        project_name="does-not-exist"
    )
    provider = GitHubProviderFactory.create(
        repository_name=pending_provider.repository_name,
        repository_owner=pending_provider.repository_owner,
        repository_owner_id=pending_provider.repository_owner_id,
        workflow_filename=pending_provider.workflow_filename,
    )

    db_request.registry.settings = {"warehouse.oidc.enabled": True}
    db_request.flags.enabled = lambda f: False
    db_request.body = json.dumps({"token": "faketoken"})
    db_request.remote_addr = "0.0.0.0"

    claims = pretend.stub()
    oidc_service = pretend.stub(
        verify_jwt_signature=pretend.call_recorder(lambda token: claims),
        find_provider=pretend.call_recorder(
            lambda claims, pending=False: pending_provider if pending else provider
        ),
        reify_pending_provider=pretend.call_recorder(lambda *a: None),
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

    db_request.find_service = find_service

    resp = views.mint_token_from_oidc(db_request)
    assert resp == {
        "success": True,
        "token": "raw-macaroon",
    }

    assert oidc_service.verify_jwt_signature.calls == [pretend.call("faketoken")]
    assert oidc_service.find_provider.calls == [
        pretend.call(claims, pending=True),
        pretend.call(claims, pending=False),
    ]
    assert oidc_service.reify_pending_provider.calls == [
        pretend.call(pending_provider, db_request.remote_addr)
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
