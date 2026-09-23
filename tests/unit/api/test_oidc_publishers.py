# SPDX-License-Identifier: Apache-2.0

import uuid

import pretend
import pytest

from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPConflict,
    HTTPForbidden,
    HTTPNotFound,
    HTTPTooManyRequests,
)
from webob.multidict import MultiDict

from tests.common.db.accounts import EmailFactory, UserFactory
from tests.common.db.oidc import (
    ActiveStatePublisherFactory,
    GitHubPublisherFactory,
    GitLabPublisherFactory,
    GooglePublisherFactory,
)
from tests.common.db.packaging import ProjectFactory, RoleFactory
from warehouse.admin.flags import AdminFlagValue
from warehouse.api import oidc_publishers as views
from warehouse.events.tags import EventTag
from warehouse.metrics import IMetricsService
from warehouse.oidc.interfaces import TooManyOIDCRegistrations
from warehouse.oidc.models import (
    ActiveStatePublisher,
    GitHubPublisher,
    GitLabPublisher,
    GooglePublisher,
    OIDCPublisher,
)
from warehouse.rate_limiting import IRateLimiter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ratelimiters(user_ok=True, ip_ok=True):
    resets = pretend.stub(total_seconds=lambda: 60)
    return {
        "user": pretend.stub(
            test=pretend.call_recorder(lambda uid: user_ok),
            hit=pretend.call_recorder(lambda uid: None),
            resets_in=pretend.call_recorder(lambda uid: resets),
        ),
        "ip": pretend.stub(
            test=pretend.call_recorder(lambda ip: ip_ok),
            hit=pretend.call_recorder(lambda ip: None),
            resets_in=pretend.call_recorder(lambda ip: resets),
        ),
    }


def _make_find_service(metrics, ratelimiters=None):
    ratelimiters = ratelimiters or _make_ratelimiters()

    def find_service(iface=None, context=None, name=""):
        if iface is IMetricsService:
            return metrics
        if iface is IRateLimiter and name == "user_oidc.publisher.register":
            return ratelimiters["user"]
        if iface is IRateLimiter and name == "ip_oidc.publisher.register":
            return ratelimiters["ip"]
        raise LookupError(f"No service: {iface!r} name={name!r}")  # pragma: no cover

    return find_service


# ---------------------------------------------------------------------------
# _multidict_from_json
# ---------------------------------------------------------------------------


class TestMultidictFromJson:
    def test_simple_fields(self):
        md = views._multidict_from_json(
            {"publisher": "github", "owner": "myorg", "environment": ""}
        )
        assert md["publisher"] == "github"
        assert md["owner"] == "myorg"
        # empty string is kept
        assert md["environment"] == ""

    def test_none_values_excluded(self):
        md = views._multidict_from_json({"owner": "myorg", "sub": None})
        assert "owner" in md
        assert "sub" not in md

    def test_non_string_coerced(self):
        md = views._multidict_from_json({"count": 42})
        assert md["count"] == "42"


# ---------------------------------------------------------------------------
# GET trusted publishers
# ---------------------------------------------------------------------------


class TestAPIGetTrustedPublishers:
    def test_empty_list(self):
        project = pretend.stub(oidc_publishers=[])
        request = pretend.stub()
        result = views.api_get_trusted_publishers(project, request)
        assert result == {"trusted_publishers": []}

    def test_with_publishers(self, monkeypatch):
        pub_id = uuid.uuid4()
        publisher = pretend.stub(
            id=pub_id,
            publisher_name="GitHub",
            publisher_url=pretend.call_recorder(
                lambda: "https://github.com/owner/repo"
            ),
        )
        monkeypatch.setattr(publisher.__class__, "__str__", lambda s: "owner/repo/.github/workflows/publish.yml")
        project = pretend.stub(oidc_publishers=[publisher])
        request = pretend.stub()

        result = views.api_get_trusted_publishers(project, request)

        assert result == {
            "trusted_publishers": [
                {
                    "id": str(pub_id),
                    "publisher_name": "GitHub",
                    "publisher_url": "https://github.com/owner/repo",
                    "specifier": "owner/repo/.github/workflows/publish.yml",
                }
            ]
        }


# ---------------------------------------------------------------------------
# POST add trusted publisher — shared behaviours
# ---------------------------------------------------------------------------


class TestAPIAddTrustedPublisher:
    def test_oidc_globally_disabled(self, metrics):
        project = pretend.stub()
        request = pretend.stub(
            find_service=_make_find_service(metrics),
            flags=pretend.stub(disallow_oidc=pretend.call_recorder(lambda f=None: True)),
            json_body={"publisher": "github"},
            user=pretend.stub(id=uuid.uuid4()),
            remote_addr="1.2.3.4",
        )

        with pytest.raises(HTTPForbidden) as exc:
            views.api_add_trusted_publisher(project, request)

        assert "temporarily disabled" in exc.value.json["error"]
        assert request.flags.disallow_oidc.calls == [pretend.call()]

    def test_unknown_publisher_type(self, metrics):
        project = pretend.stub()
        request = pretend.stub(
            find_service=_make_find_service(metrics),
            flags=pretend.stub(disallow_oidc=pretend.call_recorder(lambda f=None: False)),
            json_body={"publisher": "unknown_provider"},
            user=pretend.stub(id=uuid.uuid4()),
            remote_addr="1.2.3.4",
        )

        with pytest.raises(HTTPBadRequest) as exc:
            views.api_add_trusted_publisher(project, request)

        assert "Unknown publisher type" in exc.value.json["error"]


# ---------------------------------------------------------------------------
# POST add trusted publisher — GitHub
# ---------------------------------------------------------------------------


class TestAPIAddTrustedPublisherGitHub:
    def _make_request(self, metrics, ratelimiters, data, *, github_disabled=False):
        def disallow_oidc(flag=None):
            if flag is AdminFlagValue.DISALLOW_GITHUB_OIDC:
                return github_disabled
            return False

        return pretend.stub(
            find_service=_make_find_service(metrics, ratelimiters),
            flags=pretend.stub(disallow_oidc=pretend.call_recorder(disallow_oidc)),
            json_body=data,
            user=pretend.stub(id=uuid.uuid4(), username="testuser"),
            remote_addr="1.2.3.4",
            registry=pretend.stub(settings={"github.token": "fake-token"}),
        )

    def test_github_admin_disabled(self, metrics):
        ratelimiters = _make_ratelimiters()
        request = self._make_request(
            metrics,
            ratelimiters,
            {"publisher": "github"},
            github_disabled=True,
        )

        with pytest.raises(HTTPForbidden) as exc:
            views.api_add_trusted_publisher(pretend.stub(), request)

        assert "GitHub-based" in exc.value.json["error"]

    def test_ratelimited_by_user(self, metrics):
        ratelimiters = _make_ratelimiters(user_ok=False)
        request = self._make_request(
            metrics,
            ratelimiters,
            {"publisher": "github"},
        )

        with pytest.raises(HTTPTooManyRequests):
            views.api_add_trusted_publisher(pretend.stub(), request)

        assert metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_publisher.attempt", tags=["publisher:GitHub"]
            ),
            pretend.call(
                "warehouse.oidc.add_publisher.ratelimited", tags=["publisher:GitHub"]
            ),
        ]

    def test_ratelimited_by_ip(self, metrics):
        ratelimiters = _make_ratelimiters(user_ok=True, ip_ok=False)
        request = self._make_request(
            metrics,
            ratelimiters,
            {"publisher": "github"},
        )

        with pytest.raises(HTTPTooManyRequests):
            views.api_add_trusted_publisher(pretend.stub(), request)

    def test_form_validation_error(self, metrics, monkeypatch):
        ratelimiters = _make_ratelimiters()
        request = self._make_request(
            metrics,
            ratelimiters,
            {"publisher": "github", "owner": "", "repository": "", "workflow_filename": ""},
        )

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: False),
            errors={"owner": ["This field is required."]},
        )
        form_cls = pretend.call_recorder(lambda *a, **kw: form_obj)
        monkeypatch.setattr(views, "GitHubPublisherForm", form_cls)

        with pytest.raises(HTTPBadRequest) as exc:
            views.api_add_trusted_publisher(pretend.stub(), request)

        assert exc.value.json["errors"] == form_obj.errors

    def test_add_new_github_publisher(self, monkeypatch, db_request, metrics):
        owner = UserFactory.create()
        db_request.user = owner
        db_request.find_service = _make_find_service(metrics)
        db_request.registry.settings["github.token"] = "fake-token"

        project = ProjectFactory.create(oidc_publishers=[])
        RoleFactory.create(user=owner, project=project, role_name="Owner")
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)

        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.json_body = {
            "publisher": "github",
            "owner": "myorg",
            "repository": "myrepo",
            "workflow_filename": "publish.yml",
            "environment": "release",
        }

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            normalized_owner="myorg",
            owner_id="12345",
            repository=pretend.stub(data="myrepo"),
            workflow_filename=pretend.stub(data="publish.yml"),
            normalized_environment="release",
        )
        monkeypatch.setattr(
            views, "GitHubPublisherForm", lambda *a, **kw: form_obj
        )
        monkeypatch.setattr(
            views,
            "send_trusted_publisher_added_email",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        result = views.api_add_trusted_publisher(project, db_request)

        assert db_request.response.status == "201 Created"
        assert result["trusted_publisher"]["publisher_name"] == "GitHub"

        publisher = db_request.db.query(GitHubPublisher).one()
        assert publisher.repository_owner == "myorg"
        assert publisher.repository_name == "myrepo"
        assert publisher.workflow_filename == "publish.yml"
        assert publisher.environment == "release"
        assert publisher in project.oidc_publishers

        assert project.record_event.calls == [
            pretend.call(
                tag=EventTag.Project.OIDCPublisherAdded,
                request=db_request,
                additional={
                    "publisher": publisher.publisher_name,
                    "id": str(publisher.id),
                    "specifier": str(publisher),
                    "url": publisher.publisher_url(),
                    "submitted_by": owner.username,
                    "reified_from_pending_publisher": False,
                    "constrained_from_existing_publisher": False,
                },
            )
        ]
        assert metrics.increment.calls[-1] == pretend.call(
            "warehouse.oidc.add_publisher.ok", tags=["publisher:GitHub"]
        )

    def test_reuses_existing_github_publisher(self, monkeypatch, db_request, metrics):
        owner = UserFactory.create()
        db_request.user = owner
        db_request.find_service = _make_find_service(metrics)
        db_request.registry.settings["github.token"] = "fake-token"

        existing = GitHubPublisherFactory.create(
            repository_owner="myorg",
            repository_name="myrepo",
            workflow_filename="publish.yml",
            environment="release",
        )
        project = ProjectFactory.create(oidc_publishers=[])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)

        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.json_body = {
            "publisher": "github",
            "owner": "myorg",
            "repository": "myrepo",
            "workflow_filename": "publish.yml",
            "environment": "release",
        }

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            normalized_owner="myorg",
            owner_id="12345",
            repository=pretend.stub(data="myrepo"),
            workflow_filename=pretend.stub(data="publish.yml"),
            normalized_environment="release",
        )
        monkeypatch.setattr(views, "GitHubPublisherForm", lambda *a, **kw: form_obj)
        monkeypatch.setattr(
            views,
            "send_trusted_publisher_added_email",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        result = views.api_add_trusted_publisher(project, db_request)

        assert result["trusted_publisher"]["id"] == str(existing.id)
        # Only one publisher row exists (reused, not duplicated)
        assert db_request.db.query(GitHubPublisher).count() == 1
        assert existing in project.oidc_publishers

    def test_conflict_already_registered(self, monkeypatch, db_request, metrics):
        owner = UserFactory.create()
        db_request.user = owner
        db_request.find_service = _make_find_service(metrics)
        db_request.registry.settings["github.token"] = "fake-token"

        publisher = GitHubPublisherFactory.create(
            repository_owner="myorg",
            repository_name="myrepo",
            workflow_filename="publish.yml",
            environment="release",
        )
        project = ProjectFactory.create(oidc_publishers=[publisher])

        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.json_body = {
            "publisher": "github",
            "owner": "myorg",
            "repository": "myrepo",
            "workflow_filename": "publish.yml",
            "environment": "release",
        }

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            normalized_owner="myorg",
            owner_id="12345",
            repository=pretend.stub(data="myrepo"),
            workflow_filename=pretend.stub(data="publish.yml"),
            normalized_environment="release",
        )
        monkeypatch.setattr(views, "GitHubPublisherForm", lambda *a, **kw: form_obj)

        with pytest.raises(HTTPConflict) as exc:
            views.api_add_trusted_publisher(project, db_request)

        assert project.name in exc.value.json["error"]


# ---------------------------------------------------------------------------
# POST add trusted publisher — GitLab
# ---------------------------------------------------------------------------


class TestAPIAddTrustedPublisherGitLab:
    def _make_request(self, metrics, ratelimiters, data, *, gitlab_disabled=False):
        def disallow_oidc(flag=None):
            if flag is AdminFlagValue.DISALLOW_GITLAB_OIDC:
                return gitlab_disabled
            return False

        return pretend.stub(
            find_service=_make_find_service(metrics, ratelimiters),
            flags=pretend.stub(disallow_oidc=pretend.call_recorder(disallow_oidc)),
            json_body=data,
            user=pretend.stub(id=uuid.uuid4(), username="testuser"),
            remote_addr="1.2.3.4",
        )

    def test_gitlab_admin_disabled(self, metrics):
        def disallow_oidc(flag=None):
            return flag is AdminFlagValue.DISALLOW_GITLAB_OIDC

        request = pretend.stub(
            find_service=_make_find_service(metrics),
            flags=pretend.stub(disallow_oidc=disallow_oidc),
            json_body={"publisher": "gitlab"},
            user=pretend.stub(id=uuid.uuid4()),
            remote_addr="1.2.3.4",
            registry=pretend.stub(settings={}),
        )

        with pytest.raises(HTTPForbidden) as exc:
            views.api_add_trusted_publisher(pretend.stub(), request)

        assert "GitLab-based" in exc.value.json["error"]

    def test_ratelimited_by_user(self, metrics):
        ratelimiters = _make_ratelimiters(user_ok=False)
        request = self._make_request(metrics, ratelimiters, {"publisher": "gitlab"})

        with pytest.raises(HTTPTooManyRequests):
            views.api_add_trusted_publisher(pretend.stub(), request)

        assert metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_publisher.attempt", tags=["publisher:GitLab"]
            ),
            pretend.call(
                "warehouse.oidc.add_publisher.ratelimited", tags=["publisher:GitLab"]
            ),
        ]

    def test_ratelimited_by_ip(self, metrics):
        ratelimiters = _make_ratelimiters(user_ok=True, ip_ok=False)
        request = self._make_request(metrics, ratelimiters, {"publisher": "gitlab"})

        with pytest.raises(HTTPTooManyRequests):
            views.api_add_trusted_publisher(pretend.stub(), request)

    def test_form_validation_error(self, metrics, monkeypatch):
        ratelimiters = _make_ratelimiters()
        request = self._make_request(
            metrics,
            ratelimiters,
            {"publisher": "gitlab", "namespace": "", "project": "", "workflow_filepath": ""},
        )

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: False),
            errors={"namespace": ["This field is required."]},
        )
        monkeypatch.setattr(views, "GitLabPublisherForm", lambda *a, **kw: form_obj)
        monkeypatch.setattr(
            views.GitLabPublisher,
            "get_available_issuer_urls",
            pretend.call_recorder(lambda *a, **kw: ["https://gitlab.com"]),
        )

        with pytest.raises(HTTPBadRequest) as exc:
            views.api_add_trusted_publisher(pretend.stub(organization=None), request)

        assert exc.value.json["errors"] == form_obj.errors

    def test_add_new_gitlab_publisher(self, monkeypatch, db_request, metrics):
        owner = UserFactory.create()
        db_request.user = owner
        db_request.find_service = _make_find_service(metrics)

        project = ProjectFactory.create(oidc_publishers=[])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)

        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.json_body = {
            "publisher": "gitlab",
            "namespace": "mygroup",
            "project": "myrepo",
            "workflow_filepath": ".gitlab-ci.yml",
            "environment": "production",
            "issuer_url": "https://gitlab.com",
        }

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            namespace=pretend.stub(data="mygroup"),
            project=pretend.stub(data="myrepo"),
            workflow_filepath=pretend.stub(data=".gitlab-ci.yml"),
            normalized_environment="production",
            issuer_url=pretend.stub(data="https://gitlab.com"),
        )
        monkeypatch.setattr(views, "GitLabPublisherForm", lambda *a, **kw: form_obj)
        monkeypatch.setattr(
            views,
            "send_trusted_publisher_added_email",
            pretend.call_recorder(lambda *a, **kw: None),
        )
        monkeypatch.setattr(
            views.GitLabPublisher,
            "get_available_issuer_urls",
            pretend.call_recorder(
                lambda *a, **kw: ["https://gitlab.com"]
            ),
        )

        result = views.api_add_trusted_publisher(project, db_request)

        assert db_request.response.status == "201 Created"
        assert result["trusted_publisher"]["publisher_name"] == "GitLab"

        publisher = db_request.db.query(GitLabPublisher).one()
        assert publisher.namespace == "mygroup"
        assert publisher in project.oidc_publishers

    def test_reuses_existing_gitlab_publisher(self, monkeypatch, db_request, metrics):
        owner = UserFactory.create()
        db_request.user = owner
        db_request.find_service = _make_find_service(metrics)

        existing = GitLabPublisherFactory.create(
            namespace="mygroup",
            project="myrepo",
            workflow_filepath=".gitlab-ci.yml",
            environment="production",
            issuer_url="https://gitlab.com",
        )
        project = ProjectFactory.create(oidc_publishers=[])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)

        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.json_body = {
            "publisher": "gitlab",
            "namespace": "mygroup",
            "project": "myrepo",
            "workflow_filepath": ".gitlab-ci.yml",
            "environment": "production",
            "issuer_url": "https://gitlab.com",
        }

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            namespace=pretend.stub(data="mygroup"),
            project=pretend.stub(data="myrepo"),
            workflow_filepath=pretend.stub(data=".gitlab-ci.yml"),
            normalized_environment="production",
            issuer_url=pretend.stub(data="https://gitlab.com"),
        )
        monkeypatch.setattr(views, "GitLabPublisherForm", lambda *a, **kw: form_obj)
        monkeypatch.setattr(
            views,
            "send_trusted_publisher_added_email",
            pretend.call_recorder(lambda *a, **kw: None),
        )
        monkeypatch.setattr(
            views.GitLabPublisher,
            "get_available_issuer_urls",
            pretend.call_recorder(lambda *a, **kw: ["https://gitlab.com"]),
        )

        result = views.api_add_trusted_publisher(project, db_request)

        assert result["trusted_publisher"]["id"] == str(existing.id)
        assert db_request.db.query(GitLabPublisher).count() == 1
        assert existing in project.oidc_publishers


# ---------------------------------------------------------------------------
# POST add trusted publisher — Google
# ---------------------------------------------------------------------------


class TestAPIAddTrustedPublisherGoogle:
    def _make_request(self, metrics, ratelimiters, data, *, google_disabled=False):
        def disallow_oidc(flag=None):
            if flag is AdminFlagValue.DISALLOW_GOOGLE_OIDC:
                return google_disabled
            return False

        return pretend.stub(
            find_service=_make_find_service(metrics, ratelimiters),
            flags=pretend.stub(disallow_oidc=pretend.call_recorder(disallow_oidc)),
            json_body=data,
            user=pretend.stub(id=uuid.uuid4(), username="testuser"),
            remote_addr="1.2.3.4",
        )

    def test_google_admin_disabled(self, metrics):
        def disallow_oidc(flag=None):
            return flag is AdminFlagValue.DISALLOW_GOOGLE_OIDC

        request = pretend.stub(
            find_service=_make_find_service(metrics),
            flags=pretend.stub(disallow_oidc=disallow_oidc),
            json_body={"publisher": "google"},
            user=pretend.stub(id=uuid.uuid4()),
            remote_addr="1.2.3.4",
            registry=pretend.stub(settings={}),
        )

        with pytest.raises(HTTPForbidden) as exc:
            views.api_add_trusted_publisher(pretend.stub(), request)

        assert "Google-based" in exc.value.json["error"]

    def test_ratelimited_by_user(self, metrics):
        ratelimiters = _make_ratelimiters(user_ok=False)
        request = self._make_request(metrics, ratelimiters, {"publisher": "google"})

        with pytest.raises(HTTPTooManyRequests):
            views.api_add_trusted_publisher(pretend.stub(), request)

        assert metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_publisher.attempt", tags=["publisher:Google"]
            ),
            pretend.call(
                "warehouse.oidc.add_publisher.ratelimited", tags=["publisher:Google"]
            ),
        ]

    def test_ratelimited_by_ip(self, metrics):
        ratelimiters = _make_ratelimiters(user_ok=True, ip_ok=False)
        request = self._make_request(metrics, ratelimiters, {"publisher": "google"})

        with pytest.raises(HTTPTooManyRequests):
            views.api_add_trusted_publisher(pretend.stub(), request)

    def test_form_validation_error(self, metrics, monkeypatch):
        ratelimiters = _make_ratelimiters()
        request = self._make_request(
            metrics,
            ratelimiters,
            {"publisher": "google", "email": ""},
        )

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: False),
            errors={"email": ["This field is required."]},
        )
        monkeypatch.setattr(views, "GooglePublisherForm", lambda *a, **kw: form_obj)

        with pytest.raises(HTTPBadRequest) as exc:
            views.api_add_trusted_publisher(pretend.stub(), request)

        assert exc.value.json["errors"] == form_obj.errors

    def test_add_new_google_publisher(self, monkeypatch, db_request, metrics):
        owner = UserFactory.create()
        db_request.user = owner
        db_request.find_service = _make_find_service(metrics)

        project = ProjectFactory.create(oidc_publishers=[])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)

        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.json_body = {
            "publisher": "google",
            "email": "sa@my-project.iam.gserviceaccount.com",
            "sub": "123456",
        }

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            email=pretend.stub(data="sa@my-project.iam.gserviceaccount.com"),
            sub=pretend.stub(data="123456"),
        )
        monkeypatch.setattr(views, "GooglePublisherForm", lambda *a, **kw: form_obj)
        monkeypatch.setattr(
            views,
            "send_trusted_publisher_added_email",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        result = views.api_add_trusted_publisher(project, db_request)

        assert db_request.response.status == "201 Created"
        assert result["trusted_publisher"]["publisher_name"] == "Google"

        publisher = db_request.db.query(GooglePublisher).one()
        assert publisher.email == "sa@my-project.iam.gserviceaccount.com"
        assert publisher.sub == "123456"
        assert publisher in project.oidc_publishers

    def test_reuses_existing_google_publisher(self, monkeypatch, db_request, metrics):
        owner = UserFactory.create()
        db_request.user = owner
        db_request.find_service = _make_find_service(metrics)

        existing = GooglePublisherFactory.create(
            email="sa@my-project.iam.gserviceaccount.com",
            sub="123456",
        )
        project = ProjectFactory.create(oidc_publishers=[])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)

        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.json_body = {
            "publisher": "google",
            "email": "sa@my-project.iam.gserviceaccount.com",
            "sub": "123456",
        }

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            email=pretend.stub(data="sa@my-project.iam.gserviceaccount.com"),
            sub=pretend.stub(data="123456"),
        )
        monkeypatch.setattr(views, "GooglePublisherForm", lambda *a, **kw: form_obj)
        monkeypatch.setattr(
            views,
            "send_trusted_publisher_added_email",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        result = views.api_add_trusted_publisher(project, db_request)

        assert result["trusted_publisher"]["id"] == str(existing.id)
        assert db_request.db.query(GooglePublisher).count() == 1
        assert existing in project.oidc_publishers


# ---------------------------------------------------------------------------
# POST add trusted publisher — ActiveState
# ---------------------------------------------------------------------------


class TestAPIAddTrustedPublisherActiveState:
    def _make_request(self, metrics, ratelimiters, data, *, activestate_disabled=False):
        def disallow_oidc(flag=None):
            if flag is AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC:
                return activestate_disabled
            return False

        return pretend.stub(
            find_service=_make_find_service(metrics, ratelimiters),
            flags=pretend.stub(disallow_oidc=pretend.call_recorder(disallow_oidc)),
            json_body=data,
            user=pretend.stub(id=uuid.uuid4(), username="testuser"),
            remote_addr="1.2.3.4",
        )

    def test_activestate_admin_disabled(self, metrics):
        def disallow_oidc(flag=None):
            return flag is AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC

        request = pretend.stub(
            find_service=_make_find_service(metrics),
            flags=pretend.stub(disallow_oidc=disallow_oidc),
            json_body={"publisher": "activestate"},
            user=pretend.stub(id=uuid.uuid4()),
            remote_addr="1.2.3.4",
            registry=pretend.stub(settings={}),
        )

        with pytest.raises(HTTPForbidden) as exc:
            views.api_add_trusted_publisher(pretend.stub(), request)

        assert "ActiveState-based" in exc.value.json["error"]

    def test_ratelimited_by_user(self, metrics):
        ratelimiters = _make_ratelimiters(user_ok=False)
        request = self._make_request(metrics, ratelimiters, {"publisher": "activestate"})

        with pytest.raises(HTTPTooManyRequests):
            views.api_add_trusted_publisher(pretend.stub(), request)

        assert metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_publisher.attempt", tags=["publisher:ActiveState"]
            ),
            pretend.call(
                "warehouse.oidc.add_publisher.ratelimited",
                tags=["publisher:ActiveState"],
            ),
        ]

    def test_ratelimited_by_ip(self, metrics):
        ratelimiters = _make_ratelimiters(user_ok=True, ip_ok=False)
        request = self._make_request(metrics, ratelimiters, {"publisher": "activestate"})

        with pytest.raises(HTTPTooManyRequests):
            views.api_add_trusted_publisher(pretend.stub(), request)

    def test_form_validation_error(self, metrics, monkeypatch):
        ratelimiters = _make_ratelimiters()
        request = self._make_request(
            metrics,
            ratelimiters,
            {"publisher": "activestate", "organization": "", "project": "", "actor": ""},
        )

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: False),
            errors={"organization": ["This field is required."]},
        )
        monkeypatch.setattr(
            views, "ActiveStatePublisherForm", lambda *a, **kw: form_obj
        )

        with pytest.raises(HTTPBadRequest) as exc:
            views.api_add_trusted_publisher(pretend.stub(), request)

        assert exc.value.json["errors"] == form_obj.errors

    def test_add_new_activestate_publisher(self, monkeypatch, db_request, metrics):
        owner = UserFactory.create()
        db_request.user = owner
        db_request.find_service = _make_find_service(metrics)

        project = ProjectFactory.create(oidc_publishers=[])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)

        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        actor_id = str(uuid.uuid4())
        db_request.json_body = {
            "publisher": "activestate",
            "organization": "myorg",
            "project": "myproject",
            "actor": "myuser",
        }

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            organization=pretend.stub(data="myorg"),
            project=pretend.stub(data="myproject"),
            actor=pretend.stub(data="myuser"),
            actor_id=actor_id,
        )
        monkeypatch.setattr(
            views, "ActiveStatePublisherForm", lambda *a, **kw: form_obj
        )
        monkeypatch.setattr(
            views,
            "send_trusted_publisher_added_email",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        result = views.api_add_trusted_publisher(project, db_request)

        assert db_request.response.status == "201 Created"
        assert result["trusted_publisher"]["publisher_name"] == "ActiveState"

        publisher = db_request.db.query(ActiveStatePublisher).one()
        assert publisher.organization == "myorg"
        assert publisher.actor == "myuser"
        assert publisher in project.oidc_publishers

    def test_reuses_existing_activestate_publisher(
        self, monkeypatch, db_request, metrics
    ):
        owner = UserFactory.create()
        db_request.user = owner
        db_request.find_service = _make_find_service(metrics)

        actor_id = str(uuid.uuid4())
        existing = ActiveStatePublisherFactory.create(
            organization="myorg",
            activestate_project_name="myproject",
            actor="myuser",
            actor_id=actor_id,
        )
        project = ProjectFactory.create(oidc_publishers=[])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)

        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.json_body = {
            "publisher": "activestate",
            "organization": "myorg",
            "project": "myproject",
            "actor": "myuser",
        }

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            organization=pretend.stub(data="myorg"),
            project=pretend.stub(data="myproject"),
            actor=pretend.stub(data="myuser"),
            actor_id=actor_id,
        )
        monkeypatch.setattr(
            views, "ActiveStatePublisherForm", lambda *a, **kw: form_obj
        )
        monkeypatch.setattr(
            views,
            "send_trusted_publisher_added_email",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        result = views.api_add_trusted_publisher(project, db_request)

        assert result["trusted_publisher"]["id"] == str(existing.id)
        assert db_request.db.query(ActiveStatePublisher).count() == 1
        assert existing in project.oidc_publishers


# ---------------------------------------------------------------------------
# DELETE trusted publisher
# ---------------------------------------------------------------------------


class TestAPIDeleteTrustedPublisher:
    def test_oidc_globally_disabled(self, metrics):
        project = pretend.stub()
        request = pretend.stub(
            find_service=_make_find_service(metrics),
            flags=pretend.stub(disallow_oidc=pretend.call_recorder(lambda f=None: True)),
            matchdict={"publisher_id": str(uuid.uuid4())},
            user=pretend.stub(id=uuid.uuid4(), username="testuser"),
        )

        with pytest.raises(HTTPForbidden) as exc:
            views.api_delete_trusted_publisher(project, request)

        assert "temporarily disabled" in exc.value.json["error"]

    def test_publisher_not_found(self, metrics, db_request):
        db_request.find_service = _make_find_service(metrics)
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.matchdict = {"publisher_id": str(uuid.uuid4())}

        project = ProjectFactory.create(oidc_publishers=[])

        result = views.api_delete_trusted_publisher(project, db_request)

        assert isinstance(result, HTTPNotFound)
        assert "not found" in result.json["error"]
        assert metrics.increment.calls == [
            pretend.call("warehouse.oidc.delete_publisher.attempt")
        ]

    def test_publisher_not_on_project(self, metrics, db_request):
        db_request.user = UserFactory.create()
        db_request.find_service = _make_find_service(metrics)
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )

        publisher = GitHubPublisherFactory.create()
        db_request.db.add(publisher)
        db_request.db.flush()

        # Publisher exists in DB but is NOT on this project
        project = ProjectFactory.create(oidc_publishers=[])
        db_request.matchdict = {"publisher_id": str(publisher.id)}

        result = views.api_delete_trusted_publisher(project, db_request)

        assert isinstance(result, HTTPNotFound)

    @pytest.mark.parametrize(
        "publisher_factory",
        [
            GitHubPublisherFactory,
            GitLabPublisherFactory,
            GooglePublisherFactory,
            ActiveStatePublisherFactory,
        ],
    )
    def test_delete_publisher_entirely(
        self, monkeypatch, db_request, metrics, publisher_factory
    ):
        owner = UserFactory.create()
        EmailFactory.create(user=owner, verified=True, primary=True)
        db_request.user = owner
        db_request.find_service = _make_find_service(metrics)
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )

        publisher = publisher_factory.create()
        db_request.db.flush()

        project = ProjectFactory.create(oidc_publishers=[publisher])
        RoleFactory.create(user=owner, project=project, role_name="Owner")
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)
        db_request.matchdict = {"publisher_id": str(publisher.id)}

        monkeypatch.setattr(
            views,
            "send_trusted_publisher_removed_email",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        result = views.api_delete_trusted_publisher(project, db_request)

        assert result == {"message": f"Removed trusted publisher from {project.name}"}
        assert publisher not in project.oidc_publishers
        # Removed from DB entirely since no other projects reference it
        assert db_request.db.query(OIDCPublisher).count() == 0

        assert project.record_event.calls == [
            pretend.call(
                tag=EventTag.Project.OIDCPublisherRemoved,
                request=db_request,
                additional={
                    "publisher": publisher.publisher_name,
                    "id": str(publisher.id),
                    "specifier": str(publisher),
                    "url": publisher.publisher_url(),
                    "submitted_by": owner.username,
                },
            )
        ]
        assert metrics.increment.calls == [
            pretend.call("warehouse.oidc.delete_publisher.attempt"),
            pretend.call(
                "warehouse.oidc.delete_publisher.ok",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
        ]
        assert views.send_trusted_publisher_removed_email.calls == [
            pretend.call(
                db_request,
                owner,
                project_name=project.name,
                publisher=publisher,
            )
        ]

    def test_delete_shared_publisher_keeps_row(
        self, monkeypatch, db_request, metrics
    ):
        owner = UserFactory.create()
        EmailFactory.create(user=owner, verified=True, primary=True)
        db_request.user = owner
        db_request.find_service = _make_find_service(metrics)
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )

        publisher = GitHubPublisherFactory.create()
        db_request.db.flush()

        project = ProjectFactory.create(oidc_publishers=[publisher])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)
        other_project = ProjectFactory.create(oidc_publishers=[publisher])
        db_request.matchdict = {"publisher_id": str(publisher.id)}

        monkeypatch.setattr(
            views,
            "send_trusted_publisher_removed_email",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        views.api_delete_trusted_publisher(project, db_request)

        # Publisher is removed from this project …
        assert publisher not in project.oidc_publishers
        # … but still exists in the DB because other_project still uses it
        assert db_request.db.query(OIDCPublisher).one() == publisher
        assert publisher in other_project.oidc_publishers
