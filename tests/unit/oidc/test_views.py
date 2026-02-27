# SPDX-License-Identifier: Apache-2.0

import json

from datetime import datetime

import pretend
import pytest

from tests.common.db.accounts import UserFactory
from tests.common.db.oidc import (
    ActiveStatePublisherFactory,
    GitHubPublisherFactory,
    GitLabPublisherFactory,
    GooglePublisherFactory,
    PendingGitHubPublisherFactory,
)
from tests.common.db.organizations import OrganizationFactory
from tests.common.db.packaging import ProhibitedProjectFactory, ProjectFactory
from warehouse.events.tags import EventTag
from warehouse.macaroons import caveats
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.metrics import IMetricsService
from warehouse.oidc import errors, views
from warehouse.oidc.interfaces import IOIDCPublisherService, SignedClaims
from warehouse.oidc.models import GitHubPublisher
from warehouse.oidc.views import (
    is_from_reusable_workflow,
    should_send_environment_warning_email,
)
from warehouse.organizations.models import OrganizationProject
from warehouse.packaging import services
from warehouse.packaging.models import Project
from warehouse.rate_limiting.interfaces import IRateLimiter

from ...common.constants import (
    DUMMY_ACTIVESTATE_OIDC_JWT,
    DUMMY_GITHUB_OIDC_JWT,
    DUMMY_SEMAPHORE_OIDC_JWT,
)


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
    ("token", "service_name"),
    [
        (DUMMY_GITHUB_OIDC_JWT, "github"),
        (DUMMY_ACTIVESTATE_OIDC_JWT, "activestate"),
        (DUMMY_SEMAPHORE_OIDC_JWT, "semaphore"),
    ],
)
def test_mint_token_from_oidc_not_enabled(token, service_name, request):
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


def test_mint_token_from_oidc_jwt_decode_leaky_exception(monkeypatch):
    class Request:
        def __init__(self):
            self.response = pretend.stub(status=None)
            self.flags = pretend.stub(disallow_oidc=lambda *a: False)

        @property
        def body(self):
            return json.dumps({"token": DUMMY_GITHUB_OIDC_JWT})

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


def test_mint_token_from_oidc_unknown_issuer(metrics):
    class Request:
        def __init__(self):
            self.response = pretend.stub(status=None)
            self.flags = pretend.stub(disallow_oidc=lambda *a: False)
            self.db = pretend.stub(scalar=lambda *stmt: None)
            self.metrics = metrics

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
    assert metrics.increment.calls == [
        pretend.call(
            "warehouse.oidc.mint_token_from_oidc.unknown_issuer",
            tags=["issuer_url:nonexistent-issuer"],
        )
    ]


@pytest.mark.parametrize(
    ("token", "service_name", "unverified_issuer"),
    [
        (
            (
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL3Rva2Vu"
                "LmFjdGlvbnMuZ2l0aHVidXNlcmNvbnRlbnQuY29tIn0.saN7OFQBav8qXzgMCfERf"
                "ZWPGfHu-0EEQMlVyO5UVdQ"
            ),
            "github",
            "https://token.actions.githubusercontent.com",
        ),
        (
            (
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2FjY291b"
                "nRzLmdvb2dsZS5jb20ifQ.2RJ6Y52Rap0LEj61yBGDokUg8r92SYQq6l3cflSWBVI"
            ),
            "google",
            "https://accounts.google.com",
        ),
        (
            (
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2dpd"
                "GxhYi5jb20iLCJpYXQiOjE3MDYwMjYxNjR9.EcmGXp-aFWLrwbNm5QIjDAQ_mR"
                "sHtF7obbcnu4w_ZSU"
            ),
            "gitlab",
            "https://gitlab.com",
        ),
    ],
)
def test_mint_token_from_oidc_creates_expected_service(
    monkeypatch, token, service_name, unverified_issuer
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
    assert mint_token.calls == [
        pretend.call(oidc_service, token, unverified_issuer, request)
    ]


def test_mint_token_from_trusted_publisher_verify_jwt_signature_fails():
    claims = {"iss": "https://none"}
    oidc_service = pretend.stub(
        verify_jwt_signature=pretend.call_recorder(lambda token, issuer_url=None: None),
    )
    request = pretend.stub(
        response=pretend.stub(status=None),
        find_service=pretend.call_recorder(lambda cls, **kw: oidc_service),
        flags=pretend.stub(disallow_oidc=lambda *a: False),
    )

    response = views.mint_token(
        oidc_service, DUMMY_GITHUB_OIDC_JWT, claims["iss"], request
    )
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
        pretend.call(DUMMY_GITHUB_OIDC_JWT, claims["iss"])
    ]


def test_mint_token_trusted_publisher_lookup_fails():
    claims = {"iss": "https://none"}
    message = "some message"
    oidc_service = pretend.stub(
        verify_jwt_signature=pretend.call_recorder(
            lambda token, issuer_url=None: claims
        ),
        find_publisher=pretend.call_recorder(
            pretend.raiser(errors.InvalidPublisherError(message))
        ),
    )
    request = pretend.stub(
        response=pretend.stub(status=None),
        find_service=pretend.call_recorder(lambda cls, **kw: oidc_service),
        flags=pretend.stub(disallow_oidc=lambda *a: False),
    )

    response = views.mint_token(
        oidc_service, DUMMY_GITHUB_OIDC_JWT, claims["iss"], request
    )
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
        pretend.call(DUMMY_GITHUB_OIDC_JWT, claims["iss"])
    ]
    assert oidc_service.find_publisher.calls == [
        pretend.call(claims, pending=True),
        pretend.call(claims, pending=False),
    ]


def test_mint_token_duplicate_token():
    def find_publishers_mockup(_, pending: bool = False):
        if pending is False:
            raise errors.ReusedTokenError("some message")
        else:
            raise errors.InvalidPublisherError("some message")

    claims = {"iss": "https://none"}
    oidc_service = pretend.stub(
        verify_jwt_signature=pretend.call_recorder(
            lambda token, issuer_url=None: claims
        ),
        find_publisher=find_publishers_mockup,
    )
    request = pretend.stub(
        response=pretend.stub(status=None),
        find_service=pretend.call_recorder(lambda cls, **kw: oidc_service),
        flags=pretend.stub(disallow_oidc=lambda *a: False),
    )

    response = views.mint_token(
        oidc_service, DUMMY_GITHUB_OIDC_JWT, claims["iss"], request
    )
    assert request.response.status == 422
    assert response == {
        "message": "Token request failed",
        "errors": [
            {
                "code": "invalid-reuse-token",
                "description": "invalid token: already used",
            }
        ],
    }


def test_mint_token_pending_publisher_project_already_exists(db_request):
    project = ProjectFactory.create()
    pending_publisher = PendingGitHubPublisherFactory.create(
        project_name=project.name,
    )

    db_request.flags.disallow_oidc = lambda f=None: False

    claims = {"iss": "https://none"}
    oidc_service = pretend.stub(
        verify_jwt_signature=pretend.call_recorder(
            lambda token, issuer_url=None: claims
        ),
        find_publisher=pretend.call_recorder(
            lambda claims, pending=False: pending_publisher
        ),
    )
    db_request.find_service = pretend.call_recorder(lambda *a, **kw: oidc_service)

    resp = views.mint_token(
        oidc_service, DUMMY_GITHUB_OIDC_JWT, claims["iss"], db_request
    )
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
        pretend.call(DUMMY_GITHUB_OIDC_JWT, "https://none")
    ]
    assert oidc_service.find_publisher.calls == [pretend.call(claims, pending=True)]


def test_mint_token_from_oidc_pending_publisher_ok(monkeypatch, db_request):
    user = UserFactory.create()

    pending_publisher = PendingGitHubPublisherFactory.create(
        project_name="does-not-exist",
        added_by=user,
        repository_name="bar",
        repository_owner="foo",
        repository_owner_id="123",
        workflow_filename="example.yml",
        environment="fake",
    )

    db_request.flags.disallow_oidc = lambda f=None: False
    db_request.body = json.dumps({"token": DUMMY_GITHUB_OIDC_JWT})
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

    project = (
        db_request.db.query(Project)
        .filter(Project.name == pending_publisher.project_name)
        .one()
    )
    publisher = db_request.db.query(GitHubPublisher).one()
    event = project.events.where(
        Project.Event.tag == EventTag.Project.OIDCPublisherAdded
    ).one()
    assert event.additional == {
        "publisher": publisher.publisher_name,
        "id": str(publisher.id),
        "specifier": str(publisher),
        "url": publisher.publisher_url(),
        "submitted_by": "OpenID created token",
        "reified_from_pending_publisher": True,
        "constrained_from_existing_publisher": False,
    }


def test_mint_token_from_oidc_pending_publisher_for_organization_ok(
    monkeypatch, db_request
):
    """Test creating a project from an organization-owned pending publisher"""
    user = UserFactory.create()
    organization = OrganizationFactory.create()

    pending_publisher = PendingGitHubPublisherFactory.create(
        project_name="org-owned-project",
        added_by=user,
        repository_name="bar",
        repository_owner="foo",
        repository_owner_id="123",
        workflow_filename="example.yml",
        environment="fake",
        organization_id=organization.id,
    )

    db_request.flags.disallow_oidc = lambda f=None: False
    db_request.body = json.dumps({"token": DUMMY_GITHUB_OIDC_JWT})
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

    # Verify project was created
    project = (
        db_request.db.query(Project)
        .filter(Project.name == pending_publisher.project_name)
        .one()
    )

    # Verify project is associated with organization
    org_project = (
        db_request.db.query(OrganizationProject)
        .filter(
            OrganizationProject.organization_id == organization.id,
            OrganizationProject.project_id == project.id,
        )
        .one()
    )
    assert org_project.organization_id == organization.id
    assert org_project.project_id == project.id

    # Verify publisher was created
    publisher = db_request.db.query(GitHubPublisher).one()
    event = project.events.where(
        Project.Event.tag == EventTag.Project.OIDCPublisherAdded
    ).one()
    assert event.additional == {
        "publisher": publisher.publisher_name,
        "id": str(publisher.id),
        "specifier": str(publisher),
        "url": publisher.publisher_url(),
        "submitted_by": "OpenID created token",
        "reified_from_pending_publisher": True,
        "constrained_from_existing_publisher": False,
    }


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
        environment="fake",
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
    db_request.body = json.dumps({"token": DUMMY_GITHUB_OIDC_JWT})
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

    project = (
        db_request.db.query(Project)
        .filter(Project.name == pending_publisher.project_name)
        .one()
    )
    publisher = db_request.db.query(GitHubPublisher).one()
    event = project.events.where(
        Project.Event.tag == EventTag.Project.OIDCPublisherAdded
    ).one()
    assert event.additional == {
        "publisher": publisher.publisher_name,
        "id": str(publisher.id),
        "specifier": str(publisher),
        "url": publisher.publisher_url(),
        "submitted_by": "OpenID created token",
        "reified_from_pending_publisher": True,
        "constrained_from_existing_publisher": False,
    }


@pytest.mark.parametrize(
    ("claims_in_token", "claims_input"),
    [
        ({"ref": "someref", "sha": "somesha"}, {"ref": "someref", "sha": "somesha"}),
        ({"ref": "someref"}, {"ref": "someref", "sha": None}),
        ({"sha": "somesha"}, {"ref": None, "sha": "somesha"}),
    ],
)
def test_mint_token_no_pending_publisher_ok(
    monkeypatch, db_request, claims_in_token, claims_input
):
    # Ensure the `iss` claim is set to match the GitHub OIDC issuer, as that's
    # what the GitHubPublisherFactory implies.
    claims_in_token.update({"iss": "https://token.actions.githubusercontent.com"})

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
        verify_jwt_signature=pretend.call_recorder(
            lambda token, issuer_url=None: claims_in_token
        ),
        find_publisher=pretend.call_recorder(_find_publisher),
    )

    db_macaroon = pretend.stub(description="fakemacaroon")
    macaroon_service = pretend.stub(
        create_macaroon=pretend.call_recorder(
            lambda *a, **kw: ("raw-macaroon", db_macaroon)
        )
    )

    def find_service(iface, **kw):
        if iface == IMacaroonService:
            return macaroon_service
        else:
            pytest.fail(iface)

    monkeypatch.setattr(db_request, "find_service", find_service)
    monkeypatch.setattr(db_request, "domain", "fakedomain")

    response = views.mint_token(
        oidc_service,
        DUMMY_GITHUB_OIDC_JWT,
        "https://token.actions.githubusercontent.com",
        db_request,
    )
    assert response == {
        "success": True,
        "token": "raw-macaroon",
        "expires": 900,
    }

    assert oidc_service.verify_jwt_signature.calls == [
        pretend.call(
            DUMMY_GITHUB_OIDC_JWT, "https://token.actions.githubusercontent.com"
        )
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
                "reusable_workflow_used": False,
            },
        )
    ]


def test_mint_token_warn_constrain_environment(monkeypatch, db_request):
    claims_in_token = {
        "ref": "someref",
        "sha": "somesha",
        "environment": "fakeenv",
        "iss": "https://token.actions.githubusercontent.com",
    }
    claims_input = {"ref": "someref", "sha": "somesha"}
    time = pretend.stub(time=pretend.call_recorder(lambda: 0))
    monkeypatch.setattr(views, "time", time)
    owner = UserFactory.create()

    project = pretend.stub(
        id="fakeprojectid",
        name="fakeproject",
        record_event=pretend.call_recorder(lambda **kw: None),
        owners=[owner],
    )

    publisher = GitHubPublisherFactory(environment="")
    monkeypatch.setattr(publisher.__class__, "projects", [project])
    publisher.publisher_url = pretend.call_recorder(lambda **kw: "https://fake/url")
    # NOTE: Can't set __str__ using pretend.stub()
    monkeypatch.setattr(publisher.__class__, "__str__", lambda s: "fakespecifier")

    send_environment_ignored_in_trusted_publisher_email = pretend.call_recorder(
        lambda *a, **kw: None
    )
    monkeypatch.setattr(
        views,
        "send_environment_ignored_in_trusted_publisher_email",
        send_environment_ignored_in_trusted_publisher_email,
    )

    def _find_publisher(claims, pending=False):
        if pending:
            return None
        else:
            return publisher

    oidc_service = pretend.stub(
        verify_jwt_signature=pretend.call_recorder(
            lambda token, issuer_url=None: claims_in_token
        ),
        find_publisher=pretend.call_recorder(_find_publisher),
    )

    db_macaroon = pretend.stub(description="fakemacaroon")
    macaroon_service = pretend.stub(
        create_macaroon=pretend.call_recorder(
            lambda *a, **kw: ("raw-macaroon", db_macaroon)
        )
    )

    def find_service(iface, **kw):
        if iface == IMacaroonService:
            return macaroon_service
        else:
            pytest.fail(iface)

    monkeypatch.setattr(db_request, "find_service", find_service)
    monkeypatch.setattr(db_request, "domain", "fakedomain")

    response = views.mint_token(
        oidc_service, DUMMY_GITHUB_OIDC_JWT, claims_in_token["iss"], db_request
    )
    assert response == {
        "success": True,
        "token": "raw-macaroon",
        "expires": 900,
    }

    assert oidc_service.verify_jwt_signature.calls == [
        pretend.call(
            DUMMY_GITHUB_OIDC_JWT, "https://token.actions.githubusercontent.com"
        )
    ]
    assert oidc_service.find_publisher.calls == [
        pretend.call(claims_in_token, pending=True),
        pretend.call(claims_in_token, pending=False),
    ]

    assert send_environment_ignored_in_trusted_publisher_email.calls == [
        pretend.call(
            db_request,
            {owner},
            project_name="fakeproject",
            publisher=publisher,
            environment_name="fakeenv",
        ),
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
                "reusable_workflow_used": False,
            },
        )
    ]


def test_mint_token_with_prohibited_name_fails(monkeypatch, db_request):
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
    db_request.body = json.dumps({"token": DUMMY_GITHUB_OIDC_JWT})
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


@pytest.mark.parametrize(
    ("claims_in_token", "is_reusable", "is_github"),
    [
        (
            {
                "iss": "https://token.actions.githubusercontent.com",
                "ref": "someref",
                "sha": "somesha",
                "workflow_ref": "org/repo/.github/workflows/parent.yml@someref",
                "job_workflow_ref": "org2/repo2/.github/workflows/reusable.yml@v1",
            },
            True,
            True,
        ),
        (
            {
                "iss": "https://token.actions.githubusercontent.com",
                "ref": "someref",
                "sha": "somesha",
                "workflow_ref": "org/repo/.github/workflows/workflow.yml@someref",
                "job_workflow_ref": "org/repo/.github/workflows/workflow.yml@someref",
            },
            False,
            True,
        ),
        (
            {
                "iss": "https://gitlab.com",
                "ref": "someref",
                "sha": "somesha",
            },
            False,
            False,
        ),
    ],
)
def test_mint_token_github_reusable_workflow_metrics(
    monkeypatch,
    db_request,
    claims_in_token,
    is_reusable,
    is_github,
    metrics,
):
    time = pretend.stub(time=pretend.call_recorder(lambda: 0))
    monkeypatch.setattr(views, "time", time)

    project = pretend.stub(
        id="fakeprojectid",
        record_event=pretend.call_recorder(lambda **kw: None),
    )

    publisher = GitHubPublisherFactory() if is_github else GitLabPublisherFactory()
    monkeypatch.setattr(publisher.__class__, "projects", [project])
    # NOTE: Can't set __str__ using pretend.stub()
    monkeypatch.setattr(publisher.__class__, "__str__", lambda s: "fakespecifier")

    def _find_publisher(claims, pending=False):
        if pending:
            return None
        else:
            return publisher

    oidc_service = pretend.stub(
        verify_jwt_signature=pretend.call_recorder(
            lambda token, issuer_url=None: claims_in_token
        ),
        find_publisher=pretend.call_recorder(_find_publisher),
    )

    db_macaroon = pretend.stub(description="fakemacaroon")
    macaroon_service = pretend.stub(
        create_macaroon=pretend.call_recorder(
            lambda *a, **kw: ("raw-macaroon", db_macaroon)
        )
    )

    def find_service(iface, **kw):
        if iface == IMacaroonService:
            return macaroon_service
        elif iface == IMetricsService:
            return metrics
        else:
            pytest.fail(iface)

    monkeypatch.setattr(db_request, "find_service", find_service)
    monkeypatch.setattr(db_request, "domain", "fakedomain")

    views.mint_token(oidc_service, DUMMY_GITHUB_OIDC_JWT, claims_in_token, db_request)

    if is_reusable:
        assert metrics.increment.calls == [
            pretend.call("warehouse.oidc.mint_token.github_reusable_workflow"),
        ]
    else:
        assert not metrics.increment.calls


@pytest.mark.parametrize(
    ("is_github", "is_reusable", "claims"),
    [
        (False, False, {}),
        (
            True,
            False,
            {
                "ref": "someref",
                "sha": "somesha",
                "workflow_ref": "org/repo/.github/workflows/workflow.yml@someref",
                "job_workflow_ref": "org/repo/.github/workflows/workflow.yml@someref",
            },
        ),
        (
            True,
            True,
            {
                "ref": "someref",
                "sha": "somesha",
                "workflow_ref": "org/repo/.github/workflows/parent.yml@someref",
                "job_workflow_ref": "org2/repo2/.github/workflows/reusable.yml@v1",
            },
        ),
    ],
)
def test_is_from_reusable_workflow(
    db_request, is_github: bool, is_reusable: bool, claims: dict[str, str]
):
    publisher = GitHubPublisherFactory() if is_github else GitLabPublisherFactory()

    assert is_from_reusable_workflow(publisher, claims) == is_reusable


@pytest.mark.parametrize(
    (
        "publisher_factory",
        "publisher_environment",
        "claims_environment",
        "should_send",
    ),
    [
        # Should send for GitHub/GitLab publishers with no environment
        # configured when claims contain an environment
        (GitHubPublisherFactory, "", "new_env", True),
        (GitLabPublisherFactory, "", "new_env", True),
        # Should not send if claims don't have an environent
        (GitHubPublisherFactory, "", "", False),
        (GitLabPublisherFactory, "", "", False),
        # Should not send if publishers already have an environment
        (GitHubPublisherFactory, "env", "new_env", False),
        (GitLabPublisherFactory, "env", "new_env", False),
        # Should not send if publisher is not  GitHub/GitLab
        (ActiveStatePublisherFactory, None, "new_env", False),
        (GooglePublisherFactory, None, "new_env", False),
    ],
)
def test_should_send_environment_warning_email(
    db_request,
    publisher_factory,
    publisher_environment,
    claims_environment,
    should_send,
):
    if publisher_environment is None:
        publisher = publisher_factory()
    else:
        publisher = publisher_factory(environment=publisher_environment)

    claims = SignedClaims({"environment": claims_environment})
    assert should_send_environment_warning_email(publisher, claims) == should_send
