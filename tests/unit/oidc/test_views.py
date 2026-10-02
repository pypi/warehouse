# SPDX-License-Identifier: Apache-2.0

import http
import json
import uuid

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from tests.common.db.accounts import UserFactory
from tests.common.db.macaroons import MacaroonFactory
from tests.common.db.oidc import (
    ActiveStatePublisherFactory,
    GitHubPublisherFactory,
    GitLabPublisherFactory,
    GooglePublisherFactory,
    PendingGitHubPublisherFactory,
)
from tests.common.db.organizations import OrganizationFactory
from tests.common.db.packaging import (
    ProhibitedProjectFactory,
    ProjectFactory,
    RoleFactory,
)
from warehouse.admin.flags import AdminFlag, AdminFlagValue
from warehouse.events.tags import EventTag
from warehouse.macaroons import caveats
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons.services import DatabaseMacaroonService
from warehouse.oidc import errors, views
from warehouse.oidc.interfaces import IOIDCPublisherService, SignedClaims
from warehouse.oidc.models import GitHubPublisher
from warehouse.oidc.services import OIDCPublisherService
from warehouse.oidc.views import (
    is_from_reusable_workflow,
    should_send_environment_warning_email,
)
from warehouse.organizations.models import OrganizationProject
from warehouse.packaging import services
from warehouse.packaging.interfaces import IProjectService
from warehouse.packaging.models import Project
from warehouse.rate_limiting import DummyRateLimiter
from warehouse.rate_limiting.interfaces import IRateLimiter

from ...common.constants import DUMMY_ACTIVESTATE_OIDC_JWT, DUMMY_GITHUB_OIDC_JWT


def test_ratelimiters(pyramid_request, pyramid_services):
    user_limiter = DummyRateLimiter()
    ip_limiter = DummyRateLimiter()
    pyramid_services.register_service(
        user_limiter, IRateLimiter, None, name="user_oidc.publisher.register"
    )
    pyramid_services.register_service(
        ip_limiter, IRateLimiter, None, name="ip_oidc.publisher.register"
    )

    assert views._ratelimiters(pyramid_request) == {
        "user.oidc": user_limiter,
        "ip.oidc": ip_limiter,
    }


def test_oidc_audience_not_enabled(db_request):
    db_request.db.get(AdminFlag, AdminFlagValue.DISALLOW_OIDC.value).enabled = True

    response = views.oidc_audience(db_request)
    assert response.status_code == 403
    assert response.json == {"message": "Trusted publishing functionality not enabled"}


def test_oidc_audience(db_request):
    db_request.registry.settings["warehouse.oidc.audience"] = "fakeaudience"

    response = views.oidc_audience(db_request)
    assert response == {"audience": "fakeaudience"}


@pytest.mark.parametrize(
    ("token", "service_name"),
    [
        (DUMMY_GITHUB_OIDC_JWT, "github"),
        (DUMMY_ACTIVESTATE_OIDC_JWT, "activestate"),
    ],
)
def test_mint_token_from_oidc_not_enabled(db_request, token, service_name):
    db_request.db.get(AdminFlag, AdminFlagValue.DISALLOW_OIDC.value).enabled = True
    db_request.body = json.dumps({"token": token})

    response = views.mint_token_from_oidc(db_request)
    assert db_request.response.status_code == http.HTTPStatus.UNPROCESSABLE_ENTITY
    assert response == {
        "message": "Token request failed",
        "errors": [
            {
                "code": "not-enabled",
                "description": f"{service_name} trusted publishing functionality not enabled",  # noqa: E501
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
def test_mint_token_from_oidc_invalid_payload(db_request, body):
    db_request.body = json.dumps(body)

    resp = views.mint_token_from_oidc(db_request)

    assert db_request.response.status_code == http.HTTPStatus.UNPROCESSABLE_ENTITY
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
def test_mint_token_from_oidc_invalid_payload_malformed_jwt(db_request, body):
    db_request.body = json.dumps(body)

    resp = views.mint_token_from_oidc(db_request)

    assert db_request.response.status_code == http.HTTPStatus.UNPROCESSABLE_ENTITY
    assert resp["message"] == "Token request failed"
    assert isinstance(resp["errors"], list)
    for err in resp["errors"]:
        assert isinstance(err, dict)
        assert err["code"] == "invalid-payload"
        assert err["description"] == "malformed JWT"


def test_mint_token_from_oidc_jwt_decode_leaky_exception(mocker, db_request):
    capture_message = mocker.patch.object(
        views.sentry_sdk, "capture_message", autospec=True
    )
    mocker.patch.object(views.jwt, "decode", side_effect=ValueError("oops"))

    db_request.body = json.dumps({"token": DUMMY_GITHUB_OIDC_JWT})
    resp = views.mint_token_from_oidc(db_request)

    capture_message.assert_called_once_with("jwt.decode raised generic error: oops")

    assert db_request.response.status_code == http.HTTPStatus.UNPROCESSABLE_ENTITY
    assert resp["message"] == "Token request failed"
    assert isinstance(resp["errors"], list)
    for err in resp["errors"]:
        assert isinstance(err, dict)
        assert err["code"] == "invalid-payload"
        assert err["description"] == "malformed JWT"


def test_mint_token_from_oidc_unknown_issuer(db_request, metrics):
    db_request.body = json.dumps(
        {
            "token": (
                # iss: nonexistent-issuer
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJ"
                "ub25leGlzdGVudC1pc3N1ZXIifQ.TYGmZaQXhjS3KA8o3POV"
                "HeiD3FR5bz4X6UhRA4ykTFM"
            )
        }
    )

    resp = views.mint_token_from_oidc(db_request)

    assert db_request.response.status_code == http.HTTPStatus.UNPROCESSABLE_ENTITY
    assert resp["message"] == "Token request failed"
    assert isinstance(resp["errors"], list)
    for err in resp["errors"]:
        assert isinstance(err, dict)
        assert err["code"] == "invalid-payload"
        assert err["description"] == "unknown trusted publishing issuer"
    metrics.increment.assert_called_once_with(
        "warehouse.oidc.mint_token_from_oidc.unknown_issuer",
        tags=["issuer_url:nonexistent-issuer"],
    )


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
    mocker, db_request, token, service_name, unverified_issuer
):
    # GitLab OIDC is disallowed by default (unlike GitHub/Google/ActiveState);
    # allow it here so this test covers service selection, not the flag.
    db_request.db.get(
        AdminFlag, AdminFlagValue.DISALLOW_GITLAB_OIDC.value
    ).enabled = False

    mint_token = mocker.patch.object(views, "mint_token", autospec=True)

    oidc_service = mocker.sentinel.oidc_service
    db_request.find_service = mocker.Mock(return_value=oidc_service)
    db_request.body = json.dumps({"token": token})

    views.mint_token_from_oidc(db_request)

    db_request.find_service.assert_called_once_with(
        IOIDCPublisherService, name=service_name
    )
    mint_token.assert_called_once_with(
        oidc_service, token, unverified_issuer, db_request
    )


def test_mint_token_from_trusted_publisher_verify_jwt_signature_fails(
    mocker, pyramid_request
):
    claims = {"iss": "https://none"}
    oidc_service = mocker.create_autospec(OIDCPublisherService, instance=True)
    oidc_service.verify_jwt_signature.return_value = None

    response = views.mint_token(
        oidc_service, DUMMY_GITHUB_OIDC_JWT, claims["iss"], pyramid_request
    )
    assert pyramid_request.response.status_code == http.HTTPStatus.UNPROCESSABLE_ENTITY
    assert response == {
        "message": "Token request failed",
        "errors": [
            {
                "code": "invalid-token",
                "description": "malformed or invalid token",
            }
        ],
    }

    oidc_service.verify_jwt_signature.assert_called_once_with(
        DUMMY_GITHUB_OIDC_JWT, claims["iss"]
    )


def test_mint_token_trusted_publisher_lookup_fails(mocker, pyramid_request):
    claims = {"iss": "https://none"}
    message = "some message"
    oidc_service = mocker.create_autospec(OIDCPublisherService, instance=True)
    oidc_service.verify_jwt_signature.return_value = claims
    oidc_service.find_publisher.side_effect = errors.InvalidPublisherError(message)

    response = views.mint_token(
        oidc_service, DUMMY_GITHUB_OIDC_JWT, claims["iss"], pyramid_request
    )
    assert pyramid_request.response.status_code == http.HTTPStatus.UNPROCESSABLE_ENTITY
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

    oidc_service.verify_jwt_signature.assert_called_once_with(
        DUMMY_GITHUB_OIDC_JWT, claims["iss"]
    )
    assert oidc_service.find_publisher.call_args_list == [
        mocker.call(claims, pending=True),
        mocker.call(claims, pending=False),
    ]


def test_mint_token_duplicate_token(mocker, pyramid_request):
    def find_publishers_mockup(_, pending: bool = False):
        if pending is False:
            raise errors.ReusedTokenError("some message")
        raise errors.InvalidPublisherError("some message")

    claims = {"iss": "https://none"}
    oidc_service = mocker.create_autospec(OIDCPublisherService, instance=True)
    oidc_service.verify_jwt_signature.return_value = claims
    oidc_service.find_publisher.side_effect = find_publishers_mockup

    response = views.mint_token(
        oidc_service, DUMMY_GITHUB_OIDC_JWT, claims["iss"], pyramid_request
    )
    assert pyramid_request.response.status_code == http.HTTPStatus.UNPROCESSABLE_ENTITY
    assert response == {
        "message": "Token request failed",
        "errors": [
            {
                "code": "invalid-reuse-token",
                "description": "invalid token: already used",
            }
        ],
    }


def test_mint_token_pending_publisher_project_already_exists(mocker, db_request):
    project = ProjectFactory.create()
    pending_publisher = PendingGitHubPublisherFactory.create(
        project_name=project.name,
    )

    claims = {"iss": "https://none"}
    oidc_service = mocker.create_autospec(OIDCPublisherService, instance=True)
    oidc_service.verify_jwt_signature.return_value = claims
    oidc_service.find_publisher.return_value = pending_publisher

    resp = views.mint_token(
        oidc_service, DUMMY_GITHUB_OIDC_JWT, claims["iss"], db_request
    )
    assert db_request.response.status_code == http.HTTPStatus.UNPROCESSABLE_ENTITY
    assert resp == {
        "message": "Token request failed",
        "errors": [
            {
                "code": "invalid-pending-publisher",
                "description": "valid token, but project already exists",
            }
        ],
    }

    oidc_service.verify_jwt_signature.assert_called_once_with(
        DUMMY_GITHUB_OIDC_JWT, "https://none"
    )
    oidc_service.find_publisher.assert_called_once_with(claims, pending=True)


def test_mint_token_from_oidc_pending_publisher_ok(
    mocker, db_request, pyramid_services
):
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

    db_request.body = json.dumps({"token": DUMMY_GITHUB_OIDC_JWT})
    db_request.remote_addr = "0.0.0.0"

    ratelimiter = DummyRateLimiter()
    clear = mocker.spy(ratelimiter, "clear")
    pyramid_services.register_service(
        ratelimiter, IRateLimiter, None, name="user_oidc.publisher.register"
    )
    pyramid_services.register_service(
        ratelimiter, IRateLimiter, None, name="ip_oidc.publisher.register"
    )
    send_reified_email = mocker.patch.object(
        views, "send_pending_trusted_publisher_reified_email", autospec=True
    )

    resp = views.mint_token_from_oidc(db_request)
    assert resp["success"]
    assert resp["token"].startswith("pypi-")

    assert clear.call_args_list == [
        mocker.call(pending_publisher.added_by.id),
        mocker.call(db_request.remote_addr),
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
    send_reified_email.assert_called_once_with(
        db_request,
        user,
        project_name=pending_publisher.project_name,
        publisher_specifier=str(publisher),
    )


def test_mint_token_from_oidc_pending_publisher_for_organization_ok(
    mocker, db_request, pyramid_services
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

    db_request.body = json.dumps({"token": DUMMY_GITHUB_OIDC_JWT})
    db_request.remote_addr = "0.0.0.0"

    ratelimiter = DummyRateLimiter()
    pyramid_services.register_service(
        ratelimiter, IRateLimiter, None, name="user_oidc.publisher.register"
    )
    pyramid_services.register_service(
        ratelimiter, IRateLimiter, None, name="ip_oidc.publisher.register"
    )
    send_reified_email = mocker.patch.object(
        views, "send_pending_trusted_publisher_reified_email", autospec=True
    )

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
    send_reified_email.assert_called_once_with(
        db_request,
        user,
        project_name=pending_publisher.project_name,
        publisher_specifier=str(publisher),
    )


@pytest.mark.parametrize(
    ("resets_in", "expected_description"),
    [
        (
            timedelta(seconds=600),
            "this organization has created too many new projects recently. "
            "Try again in 600 seconds",
        ),
        (
            None,
            "this organization has created too many new projects recently",
        ),
    ],
    ids=["with-reset-hint", "without-reset-hint"],
)
@pytest.mark.parametrize(
    "limiter_method",
    ["test", "hit"],
    ids=["rejected-before-writing", "rejected-after-writing"],
)
def test_mint_token_from_oidc_pending_publisher_for_organization_ratelimited(
    db_request, mocker, resets_in, expected_description, limiter_method
):
    """`hit` rejects after the project is in the session; committing would leave
    an org-owned project whose pending publisher was never reified."""
    user = UserFactory.create()
    organization = OrganizationFactory.create()

    PendingGitHubPublisherFactory.create(
        project_name="org-owned-project",
        added_by=user,
        repository_name="bar",
        repository_owner="foo",
        repository_owner_id="123",
        workflow_filename="example.yml",
        environment="fake",
        organization_id=organization.id,
    )

    db_request.body = json.dumps({"token": DUMMY_GITHUB_OIDC_JWT})
    db_request.remote_addr = "0.0.0.0"

    org_limiter = DummyRateLimiter()
    mocker.patch.object(org_limiter, limiter_method, return_value=False)
    mocker.patch.object(org_limiter, "resets_in", return_value=resets_in)
    project_service = db_request.find_service(IProjectService)
    project_service.ratelimiters["project.create.organization"] = org_limiter

    resp = views.mint_token_from_oidc(db_request)

    assert db_request.response.status_code == 422
    assert resp == {
        "message": "Token request failed",
        "errors": [{"code": "rate-limited", "description": expected_description}],
    }
    assert db_request.tm.isDoomed()


def test_mint_token_from_pending_trusted_publisher_invalidates_others(
    mocker, db_request, pyramid_services
):
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
    stale_publishers = []
    for project_name in ["does_not_exist", "does-not-exist", "dOeS-NoT-ExISt"]:
        user = UserFactory.create()
        stale_publishers.append(
            PendingGitHubPublisherFactory.create(
                project_name=project_name,
                added_by=user,
            )
        )
        emailed_users.append(user)

    send_pending_trusted_publisher_invalidated_email = mocker.patch.object(
        services, "send_pending_trusted_publisher_invalidated_email", autospec=True
    )
    mocker.patch.object(
        views, "send_pending_trusted_publisher_reified_email", autospec=True
    )

    db_request.body = json.dumps({"token": DUMMY_GITHUB_OIDC_JWT})
    db_request.remote_addr = "0.0.0.0"

    ratelimiter = DummyRateLimiter()
    clear = mocker.spy(ratelimiter, "clear")
    pyramid_services.register_service(
        ratelimiter, IRateLimiter, None, name="user_oidc.publisher.register"
    )
    pyramid_services.register_service(
        ratelimiter, IRateLimiter, None, name="ip_oidc.publisher.register"
    )

    resp = views.mint_token_from_oidc(db_request)
    assert resp["success"]
    assert resp["token"].startswith("pypi-")

    # We should have sent one invalidation email for each pending publisher that
    # was invalidated by the minting operation. The order the emails go out in is
    # unspecified, so compare without depending on it.
    assert sorted(
        send_pending_trusted_publisher_invalidated_email.call_args_list,
        key=lambda call: call.kwargs["project_name"],
    ) == sorted(
        (
            mocker.call(db_request, user, project_name=publisher.project_name)
            for publisher, user in zip(stale_publishers, emailed_users, strict=True)
        ),
        key=lambda call: call.kwargs["project_name"],
    )

    assert clear.call_args_list == [
        mocker.call(pending_publisher.added_by.id),
        mocker.call(db_request.remote_addr),
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
    mocker, db_request, claims_in_token, claims_input
):
    # Ensure the `iss` claim is set to match the GitHub OIDC issuer, as that's
    # what the GitHubPublisherFactory implies.
    claims_in_token.update({"iss": "https://token.actions.githubusercontent.com"})

    mocker.patch.object(views, "time", SimpleNamespace(time=lambda: 0))

    project = ProjectFactory.create()
    publisher = GitHubPublisherFactory()
    publisher.projects = [project]
    db_request.db.flush()

    def _find_publisher(claims, pending=False):
        if pending:
            return None
        return publisher

    oidc_service = mocker.create_autospec(OIDCPublisherService, instance=True)
    oidc_service.verify_jwt_signature.return_value = claims_in_token
    oidc_service.find_publisher.side_effect = _find_publisher

    macaroon_service = mocker.create_autospec(DatabaseMacaroonService, instance=True)
    macaroon_service.create_macaroon.return_value = (
        "raw-macaroon",
        mocker.sentinel.db_macaroon,
    )

    def find_service(iface, **kw):
        if iface == IMacaroonService:
            return macaroon_service
        pytest.fail(iface)

    mocker.patch.object(db_request, "find_service", side_effect=find_service)
    db_request.domain = "fakedomain"

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

    oidc_service.verify_jwt_signature.assert_called_once_with(
        DUMMY_GITHUB_OIDC_JWT, "https://token.actions.githubusercontent.com"
    )
    assert oidc_service.find_publisher.call_args_list == [
        mocker.call(claims_in_token, pending=True),
        mocker.call(claims_in_token, pending=False),
    ]

    macaroon_service.create_macaroon.assert_called_once_with(
        "fakedomain",
        f"OpenID token: {publisher} ({datetime.fromtimestamp(0).isoformat()})",
        [
            caveats.OIDCPublisher(
                oidc_publisher_id=str(publisher.id),
            ),
            caveats.ProjectID(project_ids=[str(project.id)]),
            caveats.Expiration(expires_at=900, not_before=0),
        ],
        oidc_publisher_id=str(publisher.id),
        additional={"oidc": claims_input},
    )
    events = list(project.events)
    assert len(events) == 1
    assert events[0].tag == EventTag.Project.ShortLivedAPITokenAdded.value
    assert events[0].additional == {
        "expires": 900,
        "publisher_name": "GitHub",
        "publisher_url": publisher.publisher_url(),
        "reusable_workflow_used": False,
    }


def test_mint_token_warn_constrain_environment(mocker, db_request):
    claims_in_token = {
        "ref": "someref",
        "sha": "somesha",
        "environment": "fakeenv",
        "iss": "https://token.actions.githubusercontent.com",
    }
    claims_input = {"ref": "someref", "sha": "somesha"}
    mocker.patch.object(views, "time", SimpleNamespace(time=lambda: 0))

    owner = UserFactory.create()
    project = ProjectFactory.create()
    RoleFactory.create(user=owner, project=project, role_name="Owner")
    publisher = GitHubPublisherFactory(environment="")
    publisher.projects = [project]
    db_request.db.flush()

    send_environment_ignored_in_trusted_publisher_email = mocker.patch.object(
        views, "send_environment_ignored_in_trusted_publisher_email", autospec=True
    )

    def _find_publisher(claims, pending=False):
        if pending:
            return None
        return publisher

    oidc_service = mocker.create_autospec(OIDCPublisherService, instance=True)
    oidc_service.verify_jwt_signature.return_value = claims_in_token
    oidc_service.find_publisher.side_effect = _find_publisher

    macaroon_service = mocker.create_autospec(DatabaseMacaroonService, instance=True)
    macaroon_service.create_macaroon.return_value = (
        "raw-macaroon",
        mocker.sentinel.db_macaroon,
    )

    def find_service(iface, **kw):
        if iface == IMacaroonService:
            return macaroon_service
        pytest.fail(iface)

    mocker.patch.object(db_request, "find_service", side_effect=find_service)
    db_request.domain = "fakedomain"

    response = views.mint_token(
        oidc_service, DUMMY_GITHUB_OIDC_JWT, claims_in_token["iss"], db_request
    )
    assert response == {
        "success": True,
        "token": "raw-macaroon",
        "expires": 900,
    }

    oidc_service.verify_jwt_signature.assert_called_once_with(
        DUMMY_GITHUB_OIDC_JWT, "https://token.actions.githubusercontent.com"
    )
    assert oidc_service.find_publisher.call_args_list == [
        mocker.call(claims_in_token, pending=True),
        mocker.call(claims_in_token, pending=False),
    ]

    send_environment_ignored_in_trusted_publisher_email.assert_called_once_with(
        db_request,
        {owner},
        project_name=project.name,
        publisher=publisher,
        environment_name="fakeenv",
    )

    macaroon_service.create_macaroon.assert_called_once_with(
        "fakedomain",
        f"OpenID token: {publisher} ({datetime.fromtimestamp(0).isoformat()})",
        [
            caveats.OIDCPublisher(
                oidc_publisher_id=str(publisher.id),
            ),
            caveats.ProjectID(project_ids=[str(project.id)]),
            caveats.Expiration(expires_at=900, not_before=0),
        ],
        oidc_publisher_id=str(publisher.id),
        additional={"oidc": claims_input},
    )
    events = list(project.events)
    assert len(events) == 1
    assert events[0].tag == EventTag.Project.ShortLivedAPITokenAdded.value
    assert events[0].additional == {
        "expires": 900,
        "publisher_name": "GitHub",
        "publisher_url": publisher.publisher_url(),
        "reusable_workflow_used": False,
    }


def test_mint_token_with_prohibited_name_fails(mocker, db_request):
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

    db_request.body = json.dumps({"token": DUMMY_GITHUB_OIDC_JWT})
    db_request.remote_addr = "0.0.0.0"
    db_request.help_url = mocker.Mock(return_value="/the/help/url/")

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
    mocker,
    db_request,
    pyramid_services,
    claims_in_token,
    is_reusable,
    is_github,
    metrics,
):
    mocker.patch.object(views, "time", SimpleNamespace(time=lambda: 0))

    project = ProjectFactory.create()
    publisher = GitHubPublisherFactory() if is_github else GitLabPublisherFactory()
    publisher.projects = [project]
    db_request.db.flush()

    def _find_publisher(claims, pending=False):
        if pending:
            return None
        return publisher

    oidc_service = mocker.create_autospec(OIDCPublisherService, instance=True)
    oidc_service.verify_jwt_signature.return_value = claims_in_token
    oidc_service.find_publisher.side_effect = _find_publisher

    macaroon_service = mocker.create_autospec(DatabaseMacaroonService, instance=True)
    macaroon_service.create_macaroon.return_value = (
        "raw-macaroon",
        mocker.sentinel.db_macaroon,
    )
    pyramid_services.register_service(macaroon_service, IMacaroonService, None, name="")
    db_request.domain = "fakedomain"

    views.mint_token(oidc_service, DUMMY_GITHUB_OIDC_JWT, claims_in_token, db_request)

    if is_reusable:
        metrics.increment.assert_called_once_with(
            "warehouse.oidc.mint_token.github_reusable_workflow"
        )
    else:
        metrics.increment.assert_not_called()


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
        # Should not send if claims don't have an environment
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


@pytest.mark.parametrize(
    "payload",
    [
        {"token": None},
        {"token": 123},
        {"token": [123]},
        {},
    ],
)
def test_burn_oidc_issued_token_invalid_payload(pyramid_request, payload, metrics):
    pyramid_request.body = json.dumps(payload)

    response = views.burn_oidc_issued_token(pyramid_request)

    assert pyramid_request.response.status_code == http.HTTPStatus.ACCEPTED
    assert response == {"message": "Accepted", "errors": []}
    metrics.increment.assert_called_once_with(
        "warehouse.oidc.burn_oidc_issued_token",
        tags=["status:failure", "failure_reason:invalid_payload"],
    )


def test_burn_oidc_issued_token_invalid_macaroon(
    mocker, pyramid_request, pyramid_services
):
    macaroon_service = mocker.create_autospec(DatabaseMacaroonService, instance=True)
    macaroon_service.verify_signature_only.side_effect = views.InvalidMacaroonError
    pyramid_services.register_service(macaroon_service, IMacaroonService, None, name="")
    find_service = mocker.spy(pyramid_request, "find_service")

    pyramid_request.body = json.dumps({"token": "invalid-macaroon"})

    response = views.burn_oidc_issued_token(pyramid_request)

    assert pyramid_request.response.status_code == http.HTTPStatus.ACCEPTED
    assert response == {"message": "Accepted", "errors": []}
    find_service.assert_called_once_with(IMacaroonService, context=None)
    macaroon_service.verify_signature_only.assert_called_once_with("invalid-macaroon")
    pyramid_request.metrics.increment.assert_called_once_with(
        "warehouse.oidc.burn_oidc_issued_token",
        tags=["status:failure", "failure_reason:invalid_macaroon"],
    )


def test_burn_oidc_issued_token_user_macaroon(
    mocker, pyramid_request, pyramid_services
):
    user = UserFactory.build(username="fakeuser")
    macaroon = MacaroonFactory.build(id=uuid.uuid4(), user=user, oidc_publisher=None)
    macaroon_service = mocker.create_autospec(DatabaseMacaroonService, instance=True)
    macaroon_service.verify_signature_only.return_value = macaroon
    pyramid_services.register_service(macaroon_service, IMacaroonService, None, name="")
    capture_message = mocker.patch.object(
        views.sentry_sdk, "capture_message", autospec=True
    )

    pyramid_request.body = json.dumps({"token": "user-macaroon"})

    response = views.burn_oidc_issued_token(pyramid_request)

    assert pyramid_request.response.status_code == http.HTTPStatus.ACCEPTED
    assert response == {"message": "Accepted", "errors": []}
    macaroon_service.verify_signature_only.assert_called_once_with("user-macaroon")
    macaroon_service.delete_macaroon.assert_not_called()
    capture_message.assert_called_once_with(
        "Tried to burn an API token corresponding to a user: 'fakeuser'"
    )
    pyramid_request.metrics.increment.assert_called_once_with(
        "warehouse.oidc.burn_oidc_issued_token",
        tags=["status:failure", "failure_reason:not_oidc_publisher"],
    )


def test_burn_oidc_issued_token_success(mocker, db_request, pyramid_services):
    project = ProjectFactory.create()
    publisher = GitHubPublisherFactory()
    publisher.projects = [project]
    db_request.db.flush()

    macaroon_id = uuid.uuid4()
    macaroon = MacaroonFactory.build(
        id=macaroon_id, oidc_publisher=publisher, user=None
    )
    macaroon_service = mocker.create_autospec(DatabaseMacaroonService, instance=True)
    macaroon_service.verify_signature_only.return_value = macaroon
    pyramid_services.register_service(macaroon_service, IMacaroonService, None, name="")
    find_service = mocker.spy(db_request, "find_service")

    db_request.body = json.dumps({"token": "oidc-macaroon"})

    response = views.burn_oidc_issued_token(db_request)

    assert db_request.response.status_code == http.HTTPStatus.ACCEPTED
    assert response == {"message": "Accepted", "errors": []}
    find_service.assert_called_once_with(IMacaroonService, context=None)
    macaroon_service.verify_signature_only.assert_called_once_with("oidc-macaroon")
    macaroon_service.delete_macaroon.assert_called_once_with(str(macaroon_id))
    db_request.metrics.increment.assert_called_once_with(
        "warehouse.oidc.burn_oidc_issued_token",
        tags=["status:success", "publisher_name:GitHub"],
    )

    event = project.events.where(
        Project.Event.tag == EventTag.Project.ShortLivedAPITokenRevoked
    ).one()
    assert event.additional == {}


def test_mint_token_jti_stored_before_macaroon_creation(mocker, db_request):
    """
    Verify that the JTI is atomically claimed before the macaroon is minted,
    so that a second request carrying the same JWT cannot also mint a token.

    The JTI anti-replay must use a single atomic SET-if-not-exists operation
    *before* any macaroon is created. If the store happens after macaroon
    creation, two concurrent callers could both observe the JTI as unused,
    both mint tokens, and only the first store would succeed.
    """
    jti_value = "6e67b1cb-2b8d-4be5-91cb-757edb2ec970"
    claims = SignedClaims(
        {
            "ref": "someref",
            "sha": "somesha",
            "iss": "https://token.actions.githubusercontent.com",
            "jti": jti_value,
            "exp": 9999999999,
        }
    )

    project = ProjectFactory.create()
    publisher = GitHubPublisherFactory()
    publisher.projects = [project]
    db_request.db.flush()

    # Track the order of operations to verify JTI is stored before macaroon
    # creation. Each call appends to this list so we can assert ordering.
    operation_log: list[str] = []

    def fake_store_jwt_identifier(jti, expiration):
        operation_log.append("store_jti")
        return True

    def _find_publisher(signed_claims, pending=False):
        if pending:
            return None
        return publisher

    oidc_service = mocker.create_autospec(OIDCPublisherService, instance=True)
    oidc_service.verify_jwt_signature.return_value = claims
    oidc_service.find_publisher.side_effect = _find_publisher
    oidc_service.store_jwt_identifier.side_effect = fake_store_jwt_identifier

    def fake_create_macaroon(*a, **kw):
        operation_log.append("create_macaroon")
        return ("raw-macaroon", mocker.sentinel.db_macaroon)

    macaroon_service = mocker.create_autospec(DatabaseMacaroonService, instance=True)
    macaroon_service.create_macaroon.side_effect = fake_create_macaroon

    def find_service(iface, **kw):
        if iface == IMacaroonService:
            return macaroon_service
        pytest.fail(f"Unexpected service lookup: {iface}")

    mocker.patch.object(db_request, "find_service", side_effect=find_service)
    db_request.domain = "fakedomain"

    # First request should succeed
    response1 = views.mint_token(
        oidc_service,
        DUMMY_GITHUB_OIDC_JWT,
        "https://token.actions.githubusercontent.com",
        db_request,
    )
    assert response1["success"] is True
    assert response1["token"] == "raw-macaroon"

    # Verify the JTI was stored BEFORE the macaroon was created.
    # If store_jti comes after create_macaroon, there is a window where
    # a concurrent request could also pass the existence check.
    store_idx = operation_log.index("store_jti")
    create_idx = operation_log.index("create_macaroon")
    assert store_idx < create_idx, (
        "JTI must be stored before macaroon creation to prevent "
        "concurrent requests from both minting tokens. "
        f"Got operation order: {operation_log}"
    )

    # Simulate a concurrent request where find_publisher's EXISTS check passes
    # (both requests see the JTI as unused) but the atomic store_jwt_identifier
    # rejects the second request because SET NX fails.
    operation_log.clear()
    db_request.response.status = 200

    oidc_service_race = mocker.create_autospec(OIDCPublisherService, instance=True)
    oidc_service_race.verify_jwt_signature.return_value = claims
    oidc_service_race.find_publisher.side_effect = _find_publisher
    # Simulate: SET NX returns False because the other request stored it first
    oidc_service_race.store_jwt_identifier.return_value = False

    response2 = views.mint_token(
        oidc_service_race,
        DUMMY_GITHUB_OIDC_JWT,
        "https://token.actions.githubusercontent.com",
        db_request,
    )
    assert str(http.HTTPStatus.UNPROCESSABLE_ENTITY) in str(db_request.response.status)
    assert response2["errors"][0]["code"] == "invalid-reuse-token"
