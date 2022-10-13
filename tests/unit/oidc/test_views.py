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

import pretend
import pytest

from warehouse.macaroons import caveats
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.oidc import views
from warehouse.oidc.interfaces import IOIDCProviderService


def test_mint_token_from_oidc_invalid_json():
    class Request:
        def __init__(self):
            self.response = pretend.stub(status=None)

        @property
        def json_body(self):
            raise ValueError

    req = Request()
    resp = views.mint_token_from_oidc(req)
    assert req.response.status == 422
    assert resp == {
        "message": "Token request failed",
        "errors": [{"code": "invalid-json", "description": "missing JSON body"}],
    }


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"token": ""},
        {"token": None},
        {"token": 0},
        {"token": [""]},
        {"token": []},
        {"token": {}},
        {"wrongkey": ""},
    ],
)
def test_mint_token_from_oidc_missing_token(body):
    request = pretend.stub(response=pretend.stub(status=None), json_body=body)
    resp = views.mint_token_from_oidc(request)
    assert request.response.status == 422
    assert resp == {
        "message": "Token request failed",
        "errors": [{"code": "invalid-token", "description": "missing or empty token"}],
    }


def test_mint_token_from_oidc_provider_lookup_fails():
    oidc_service = pretend.stub(find_provider=pretend.call_recorder(lambda token: None))
    request = pretend.stub(
        response=pretend.stub(status=None),
        json_body={"token": "faketoken"},
        find_service=pretend.call_recorder(lambda cls, **kw: oidc_service),
    )

    response = views.mint_token_from_oidc(request)
    assert request.response.status == 422
    assert response == {
        "message": "Token request failed",
        "errors": [
            {"code": "invalid-token", "description": "malformed or invalid token"}
        ],
    }

    assert request.find_service.calls == [
        pretend.call(IOIDCProviderService, name="github")
    ]
    assert oidc_service.find_provider.calls == [pretend.call("faketoken")]


def test_mint_token_from_oidc_ok(monkeypatch):
    time = pretend.stub(time=pretend.call_recorder(lambda: 0))
    monkeypatch.setattr(views, "time", time)

    project = pretend.stub(
        id="fakeprojectid",
        record_event=pretend.call_recorder(lambda **kw: None),
    )
    provider = pretend.stub(
        id="fakeproviderid",
        projects=[project],
    )
    # NOTE: Can't set __str__ using pretend.stub()
    monkeypatch.setattr(provider.__class__, "__str__", lambda s: "fakespecifier")

    oidc_service = pretend.stub(
        find_provider=pretend.call_recorder(lambda token: provider)
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
        json_body={"token": "faketoken"},
        find_service=find_service,
        domain="fakedomain",
        remote_addr="0.0.0.0",
    )

    response = views.mint_token_from_oidc(request)
    assert response == {
        "success": True,
        "token": "raw-macaroon",
    }

    assert oidc_service.find_provider.calls == [pretend.call("faketoken")]
    assert macaroon_service.create_macaroon.calls == [
        pretend.call(
            "fakedomain",
            "OpenID token: fakespecifier (0)",
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
            tag="project:api_token:added",
            ip_address="0.0.0.0",
            additional={
                "description": "fakemacaroon",
                "expires": 900,
            },
        )
    ]
