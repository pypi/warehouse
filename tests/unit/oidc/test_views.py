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
from tests.common.db.oidc import GitHubPublisherFactory, PendingGitHubPublisherFactory
from tests.common.db.packaging import ProhibitedProjectFactory, ProjectFactory
from warehouse.events.tags import EventTag
from warehouse.macaroons import caveats
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.oidc import errors, views
from warehouse.oidc.interfaces import IOIDCPublisherService
from warehouse.packaging import services
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


@pytest.mark.parametrize(
    "token_fixture_name,service_name",
    [
        ("dummy_github_oidc_jwt", "github"),
        ("dummy_activestate_oidc_jwt", "activestate"),
    ],
)
def test_mint_token_from_oidc_not_enabled(token_fixture_name, service_name, request):
    token = request.getfixturevalue(token_fixture_name)
    request = pretend.stub(
        body=json.dumps({"token": token}),
        response=pretend.stub(status=None),
        flags=pretend.stub(disallow_oidc=lambda *a: True),
    )

    response = views.mint_token_from_oidc(request)
    assert request.response.status == 422
    assert response == {
        "message": "Token request failed",
        "errors": [
            {
                "code": "not-enabled",
                "description": f"{service_name} trusted publishing functionality not enabled",  # noqa
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
def test_mint_token_from_oidc_invalid_payload(body):
    class Request:
        def __init__(self):
            self.response = pretend.stub(status=None)
            self.flags = pretend.stub(disallow_oidc=lambda *a: False)

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


@pytest.mark.parametrize(
    "body",
    [
        {"token": "not-a-jwt"},
        {
            # Well-formed JWT, but no `iss` claim
            "token": (
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwib"
                "mFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fw"
                "pMeJf36POk6yJV_adQssw5c"
            )
        },
    ],
)
def test_mint_token_from_oidc_invalid_payload_malformed_jwt(body):
    class Request:
        def __init__(self):
            self.response = pretend.stub(status=None)
            self.flags = pretend.stub(disallow_oidc=lambda *a: False)

        @property
        def body(self):
            return json.dumps(body)

        def find_service(self, *a, **kw):
            return pretend.stub(increment=pretend.call_recorder(lambda s: None))

    req = Request()
    resp = views.mint_token_from_oidc(req)

    assert req.response.status == 422
    assert resp["message"] == "Token request failed"
    assert isinstance(resp["errors"], list)
    for err in resp["errors"]:
        assert isinstance(err, dict)
        assert err["code"] == "invalid-payload"
        assert err["description"] == "malformed JWT"


def test_mint_token_from_oidc_jwt_decode_leaky_exception(
    monkeypatch, dummy_github_oidc_jwt: str
):
    class Request:
        def __init__(self):
            self.response = pretend.stub(status=None)
            self.flags = pretend.stub(disallow_oidc=lambda *a: False)

        @property
        def body(self):
            return json.dumps({"token": dummy_github_oidc_jwt})

        def find_service(self, *a, **kw):
            return pretend.stub(increment=pretend.call_recorder(lambda s: None))

    capture_message = pretend.call_recorder(lambda s: None)
    monkeypatch.setattr(views.sentry_sdk, "capture_message", capture_message)
    monkeypatch.setattr(views.jwt, "decode", pretend.raiser(ValueError("oops")))

    req = Request()
    resp = views.mint_token_from_oidc(req)

    assert capture_message.calls == [
        pretend.call("jwt.decode raised generic error: oops")
    ]

    assert req.response.status == 422
    assert resp["message"] == "Token request failed"
    assert isinstance(resp["errors"], list)
    for err in resp["errors"]:
        assert isinstance(err, dict)
        assert err["code"] == "invalid-payload"
        assert err["description"] == "malformed JWT"


def test_mint_token_from_oidc_unknown_issuer():
    class Request:
        def __init__(self):
            self.response = pretend.stub(status=None)
            self.flags = pretend.stub(disallow_oidc=lambda *a: False)

        @property
        def body(self):
            return json.dumps(
                {
                    "token": (
                        # iss: nonexistent-issuer
                        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJ"
                        "ub25leGlzdGVudC1pc3N1ZXIifQ.TYGmZaQXhjS3KA8o3POV"
                        "HeiD3FR5bz4X6UhRA4ykTFM"
                    )
                }
            )

    req = Request()
    resp = views.mint_token_from_oidc(req)

    assert req.response.status == 422
    assert resp["message"] == "Token request failed"
    assert isinstance(resp["errors"], list)
    for err in resp["errors"]:
        assert isinstance(err, dict)
        assert err["code"] == "invalid-payload"
        assert err["description"] == "unknown trusted publishing issuer"


@pytest.mark.parametrize(
    ("token", "service_name"),
    [
        (
            (
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL3Rva2Vu"
                "LmFjdGlvbnMuZ2l0aHVidXNlcmNvbnRlbnQuY29tIn0.saN7OFQBav8qXzgMCfERf"
                "ZWPGfHu-0EEQMlVyO5UVdQ"
            ),
            "github",
        ),
        (
            (
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2FjY291b"
                "nRzLmdvb2dsZS5jb20ifQ.2RJ6Y52Rap0LEj61yBGDokUg8r92SYQq6l3cflSWBVI"
            ),
            "google",
        ),
        (
            (
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2dpd"
                "GxhYi5jb20iLCJpYXQiOjE3MDYwMjYxNjR9.EcmGXp-aFWLrwbNm5QIjDAQ_mR"
                "sHtF7obbcnu4w_ZSU"
            ),
            "gitlab",
        ),
    ],
)
def test_mint_token_from_oidc_creates_expected_service(
    monkeypatch, token, service_name
):
    mint_token = pretend.call_recorder(lambda *a: pretend.stub())
    monkeypatch.setattr(views, "mint_token", mint_token)

    oidc_service = pretend.stub()
    request = pretend.stub(
        response=pretend.stub(status=None),
        find_service=pretend.call_recorder(lambda cls, **kw: oidc_service),
        flags=pretend.stub(disallow_oidc=lambda *a: False),
        body=json.dumps({"token": token}),
    )

    views.mint_token_from_oidc(request)

    assert request.find_service.calls == [
        pretend.call(IOIDCPublisherService, name=service_name)
    ]
    assert mint_token.calls == [pretend.call(oidc_service, token, request)]


def test_mint_token_from_trusted_publisher_verify_jwt_signature_fails(
    dummy_github_oidc_jwt,
):
    oidc_service = pretend.stub(
        verify_jwt_signature=pretend.call_recorder(lambda token: None),
    )
    request = pretend.stub(
        response=pretend.stub(status=None),
        find_service=pretend.call_recorder(lambda cls, **kw: oidc_service),
        flags=pretend.stub(disallow_oidc=lambda *a: False),
    )

    response = views.mint_token(oidc_service, dummy_github_oidc_jwt, request)
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

    assert oidc_service.verify_jwt_signature.calls == [
        pretend.call(dummy_github_oidc_jwt)
    ]


def test_mint_token_trusted_publisher_lookup_fails(dummy_github_oidc_jwt):
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
        find_service=pretend.call_recorder(lambda cls, **kw: oidc_service),
        flags=pretend.stub(disallow_oidc=lambda *a: False),
    )

    response = views.mint_token(oidc_service, dummy_github_oidc_jwt, request)
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

    assert oidc_service.verify_jwt_signature.calls == [
        pretend.call(dummy_github_oidc_jwt)
    ]
    assert oidc_service.find_publisher.calls == [
        pretend.call(claims, pending=True),
        pretend.call(claims, pending=False),
    ]


def test_mint_token_pending_publisher_project_already_exists(
    db_request, dummy_github_oidc_jwt
):
    project = ProjectFactory.create()
    pending_publisher = PendingGitHubPublisherFactory.create(
        project_name=project.name,
    )

    db_request.flags.disallow_oidc = lambda f=None: False

    claims = pretend.stub()
    oidc_service = pretend.stub(
        verify_jwt_signature=pretend.call_recorder(lambda token: claims),
        find_publisher=pretend.call_recorder(
            lambda claims, pending=False: pending_publisher
        ),
    )
    db_request.find_service = pretend.call_recorder(lambda *a, **kw: oidc_service)

    resp = views.mint_token(oidc_service, dummy_github_oidc_jwt, db_request)
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

    assert oidc_service.verify_jwt_signature.calls == [
        pretend.call(dummy_github_oidc_jwt)
    ]
    assert oidc_service.find_publisher.calls == [pretend.call(claims, pending=True)]


def test_mint_token_from_oidc_pending_publisher_ok(
    monkeypatch,
    db_request,
    dummy_github_oidc_jwt,
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
    db_request.body = json.dumps({"token": dummy_github_oidc_jwt})
    db_request.remote_addr = "0.0.0.0"

    ratelimiter = pretend.stub(clear=pretend.call_recorder(lambda id: None))
    ratelimiters = {
        "user.oidc": ratelimiter,
        "ip.oidc": ratelimiter,
    }
    monkeypatch.setattr(views, "_ratelimiters", lambda r: ratelimiters)

    resp = views.mint_token_from_oidc(db_request)
    assert resp["success"]
    assert resp["token"].startswith("pypi-")

    assert ratelimiter.clear.calls == [
        pretend.call(pending_publisher.added_by.id),
        pretend.call(db_request.remote_addr),
    ]


def test_mint_token_from_pending_trusted_publisher_invalidates_others(
    monkeypatch, db_request, dummy_github_oidc_jwt
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
        services,
        "send_pending_trusted_publisher_invalidated_email",
        send_pending_trusted_publisher_invalidated_email,
    )

    db_request.flags.oidc_enabled = lambda f: False
    db_request.body = json.dumps({"token": dummy_github_oidc_jwt})
    db_request.remote_addr = "0.0.0.0"

    ratelimiter = pretend.stub(clear=pretend.call_recorder(lambda id: None))
    ratelimiters = {
        "user.oidc": ratelimiter,
        "ip.oidc": ratelimiter,
    }
    monkeypatch.setattr(views, "_ratelimiters", lambda r: ratelimiters)

    resp = views.mint_token_from_oidc(db_request)
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
def test_mint_token_no_pending_publisher_ok(
    monkeypatch, db_request, claims_in_token, claims_input, dummy_github_oidc_jwt
):
    time = pretend.stub(time=pretend.call_recorder(lambda: 0))
    monkeypatch.setattr(views, "time", time)

    project = pretend.stub(
        id="fakeprojectid",
        record_event=pretend.call_recorder(lambda **kw: None),
    )

    publisher = GitHubPublisherFactory()
    monkeypatch.setattr(publisher.__class__, "projects", [project])
    publisher.publisher_url = pretend.call_recorder(lambda **kw: "https://fake/url")
    # NOTE: Can't set __str__ using pretend.stub()
    monkeypatch.setattr(publisher.__class__, "__str__", lambda s: "fakespecifier")

    def _find_publisher(claims, pending=False):
        if pending:
            return None
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

    monkeypatch.setattr(db_request, "find_service", find_service)
    monkeypatch.setattr(db_request, "domain", "fakedomain")

    response = views.mint_token(oidc_service, dummy_github_oidc_jwt, db_request)
    assert response == {
        "success": True,
        "token": "raw-macaroon",
    }

    assert oidc_service.verify_jwt_signature.calls == [
        pretend.call(dummy_github_oidc_jwt)
    ]
    assert oidc_service.find_publisher.calls == [
        pretend.call(claims_in_token, pending=True),
        pretend.call(claims_in_token, pending=False),
    ]

    assert macaroon_service.create_macaroon.calls == [
        pretend.call(
            "fakedomain",
            f"OpenID token: fakespecifier ({datetime.fromtimestamp(0).isoformat()})",
            [
                caveats.OIDCPublisher(
                    oidc_publisher_id=str(publisher.id),
                ),
                caveats.ProjectID(project_ids=["fakeprojectid"]),
                caveats.Expiration(expires_at=900, not_before=0),
            ],
            oidc_publisher_id=str(publisher.id),
            additional={"oidc": claims_input},
        )
    ]
    assert project.record_event.calls == [
        pretend.call(
            tag=EventTag.Project.ShortLivedAPITokenAdded,
            request=db_request,
            additional={
                "expires": 900,
                "publisher_name": "GitHub",
                "publisher_url": "https://fake/url",
            },
        )
    ]


def test_mint_token_with_prohibited_name_fails(
    monkeypatch,
    db_request,
    dummy_github_oidc_jwt,
):
    prohibited_project_name = ProhibitedProjectFactory.create()
    user = UserFactory.create()
    PendingGitHubPublisherFactory.create(
        project_name=prohibited_project_name.name,
        added_by=user,
        repository_name="bar",
        repository_owner="foo",
        repository_owner_id="123",
        workflow_filename="example.yml",
        environment="",
    )

    db_request.flags.disallow_oidc = lambda f=None: False
    db_request.body = json.dumps({"token": dummy_github_oidc_jwt})
    db_request.remote_addr = "0.0.0.0"
    db_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")

    ratelimiter = pretend.stub(clear=pretend.call_recorder(lambda id: None))
    ratelimiters = {
        "user.oidc": ratelimiter,
        "ip.oidc": ratelimiter,
    }
    monkeypatch.setattr(views, "_ratelimiters", lambda r: ratelimiters)

    resp = views.mint_token_from_oidc(db_request)

    assert resp["message"] == "Token request failed"
    assert isinstance(resp["errors"], list)
    for err in resp["errors"]:
        assert isinstance(err, dict)
        assert err["code"] == "invalid-payload"
        assert err["description"] == (
            f"The name {prohibited_project_name.name!r} isn't allowed. "
            "See /the/help/url/ "
            "for more information."
        )


def test_mint_token_with_invalid_name_fails(
    monkeypatch,
    db_request,
    dummy_github_oidc_jwt,
):
    user = UserFactory.create()
    pending_publisher = PendingGitHubPublisherFactory.create(
        project_name="-foo-",
        added_by=user,
        repository_name="bar",
        repository_owner="foo",
        repository_owner_id="123",
        workflow_filename="example.yml",
        environment="",
    )

    db_request.flags.disallow_oidc = lambda f=None: False
    db_request.body = json.dumps({"token": dummy_github_oidc_jwt})
    db_request.remote_addr = "0.0.0.0"

    ratelimiter = pretend.stub(clear=pretend.call_recorder(lambda id: None))
    ratelimiters = {
        "user.oidc": ratelimiter,
        "ip.oidc": ratelimiter,
    }
    monkeypatch.setattr(views, "_ratelimiters", lambda r: ratelimiters)

    resp = views.mint_token_from_oidc(db_request)

    assert resp["message"] == "Token request failed"
    assert isinstance(resp["errors"], list)
    for err in resp["errors"]:
        assert isinstance(err, dict)
        assert err["code"] == "invalid-payload"
        assert err["description"] == (
            f"The name {pending_publisher.project_name!r} is invalid."
        )
