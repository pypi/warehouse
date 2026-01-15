# SPDX-License-Identifier: Apache-2.0

import uuid

import pretend
import pytest

from pyramid.httpexceptions import HTTPSeeOther, HTTPTooManyRequests
from webob.multidict import MultiDict

from tests.common.db.accounts import EmailFactory, UserFactory
from tests.common.db.packaging import ProjectFactory, RoleFactory
from warehouse.admin.flags import AdminFlagValue
from warehouse.events.tags import EventTag
from warehouse.manage.views import oidc_publishers as oidc_views
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


class TestManageOIDCPublisherViews:
    def test_initializes(self, metrics):
        project = pretend.stub(organization=None)
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda *a, **kw: metrics),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                },
            ),
            POST=MultiDict(),
        )
        view = oidc_views.ManageOIDCPublisherViews(project, request)

        assert view.project is project
        assert view.request is request
        assert view.metrics is metrics

        assert view.request.find_service.calls == [
            pretend.call(IMetricsService, context=None)
        ]

    @pytest.mark.parametrize(
        ("ip_exceeded", "user_exceeded"),
        [
            (False, False),
            (False, True),
            (True, False),
        ],
    )
    def test_ratelimiting(self, metrics, ip_exceeded, user_exceeded):
        project = pretend.stub(organization=None)
        user_rate_limiter = pretend.stub(
            hit=pretend.call_recorder(lambda *a, **kw: None),
            test=pretend.call_recorder(lambda uid: not user_exceeded),
            resets_in=pretend.call_recorder(lambda uid: pretend.stub()),
        )
        ip_rate_limiter = pretend.stub(
            hit=pretend.call_recorder(lambda *a, **kw: None),
            test=pretend.call_recorder(lambda ip: not ip_exceeded),
            resets_in=pretend.call_recorder(lambda uid: pretend.stub()),
        )

        def find_service(iface, name=None, context=None):
            if iface is IMetricsService:
                return metrics

            if name == "user_oidc.publisher.register":
                return user_rate_limiter
            else:
                return ip_rate_limiter

        request = pretend.stub(
            find_service=pretend.call_recorder(find_service),
            user=pretend.stub(id=pretend.stub()),
            remote_addr=pretend.stub(),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                },
            ),
            POST=MultiDict(),
        )

        view = oidc_views.ManageOIDCPublisherViews(project, request)

        assert view._ratelimiters == {
            "user.oidc": user_rate_limiter,
            "ip.oidc": ip_rate_limiter,
        }
        assert request.find_service.calls == [
            pretend.call(IMetricsService, context=None),
            pretend.call(IRateLimiter, name="user_oidc.publisher.register"),
            pretend.call(IRateLimiter, name="ip_oidc.publisher.register"),
        ]

        view._hit_ratelimits()

        assert user_rate_limiter.hit.calls == [
            pretend.call(request.user.id),
        ]
        assert ip_rate_limiter.hit.calls == [pretend.call(request.remote_addr)]

        if user_exceeded or ip_exceeded:
            with pytest.raises(TooManyOIDCRegistrations):
                view._check_ratelimits()
        else:
            view._check_ratelimits()

    def test_manage_project_oidc_publishers(self, monkeypatch):
        project = pretend.stub(oidc_publishers=[], organization=None)
        request = pretend.stub(
            user=pretend.stub(),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                },
            ),
            find_service=lambda *a, **kw: None,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            POST=MultiDict(),
        )

        view = oidc_views.ManageOIDCPublisherViews(project, request)
        assert view.manage_project_oidc_publishers() == {
            "disabled": {
                "GitHub": False,
                "GitLab": False,
                "Google": False,
                "ActiveState": False,
                "CircleCI": False,
            },
            "project": project,
            "github_publisher_form": view.github_publisher_form,
            "gitlab_publisher_form": view.gitlab_publisher_form,
            "google_publisher_form": view.google_publisher_form,
            "activestate_publisher_form": view.activestate_publisher_form,
            "circleci_publisher_form": view.circleci_publisher_form,
            "prefilled_provider": view.prefilled_provider,
        }

        assert request.flags.disallow_oidc.calls == [
            pretend.call(),
            pretend.call(AdminFlagValue.DISALLOW_GITHUB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GITLAB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GOOGLE_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_CIRCLECI_OIDC),
        ]

    def test_manage_project_oidc_publishers_admin_disabled(
        self, monkeypatch, pyramid_request
    ):
        project = pretend.stub(oidc_publishers=[], organization=None)
        pyramid_request.user = pretend.stub()
        pyramid_request.registry = pretend.stub(
            settings={
                "github.token": "fake-api-token",
            },
        )
        pyramid_request.find_service = lambda *a, **kw: None
        pyramid_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: True)
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        pyramid_request.POST = MultiDict()

        view = oidc_views.ManageOIDCPublisherViews(project, pyramid_request)

        assert view.manage_project_oidc_publishers() == {
            "disabled": {
                "GitHub": True,
                "GitLab": True,
                "Google": True,
                "ActiveState": True,
                "CircleCI": True,
            },
            "project": project,
            "github_publisher_form": view.github_publisher_form,
            "gitlab_publisher_form": view.gitlab_publisher_form,
            "google_publisher_form": view.google_publisher_form,
            "activestate_publisher_form": view.activestate_publisher_form,
            "circleci_publisher_form": view.circleci_publisher_form,
            "prefilled_provider": view.prefilled_provider,
        }

        assert pyramid_request.flags.disallow_oidc.calls == [
            pretend.call(),
            pretend.call(AdminFlagValue.DISALLOW_GITHUB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GITLAB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GOOGLE_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_CIRCLECI_OIDC),
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                (
                    "Trusted publishing is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
        ]

    @pytest.mark.parametrize(
        ("form_name", "prefilled_data"),
        [
            # All fields of GitHub provider
            (
                "github_publisher_form",
                {
                    "provider": "github",
                    "owner": "owner",
                    "repository": "repo",
                    "workflow_filename": "file.yml",
                    "environment": "my_env",
                },
            ),
            # All fields of GitLab provider
            (
                "gitlab_publisher_form",
                {
                    "provider": "gitlab",
                    "namespace": "owner",
                    "project": "repo",
                    "workflow_filepath": "file.yml",
                    "environment": "my_env",
                    "issuer_url": "https://gitlab.com",
                },
            ),
            # All fields of Google provider
            (
                "google_publisher_form",
                {
                    "provider": "google",
                    "email": "email@example.com",
                    "sub": "my_subject",
                },
            ),
            # All fields of ActiveState provider
            (
                "activestate_publisher_form",
                {
                    "provider": "activestate",
                    "organization": "my_org",
                    "project": "my_project",
                    "actor": "my_actor",
                },
            ),
            # All fields of GitHub provider, case-insensitive
            (
                "github_publisher_form",
                {
                    "provider": "GitHub",
                    "owner": "owner",
                    "repository": "repo",
                    "workflow_filename": "file.yml",
                    "environment": "my_env",
                },
            ),
        ],
    )
    def test_manage_project_oidc_publishers_prefill(
        self, monkeypatch, form_name, prefilled_data
    ):
        project = pretend.stub(oidc_publishers=[], organization=None)
        request = pretend.stub(
            user=pretend.stub(),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                },
            ),
            find_service=lambda *a, **kw: None,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            POST=MultiDict(),
            params=MultiDict(prefilled_data),
        )

        view = oidc_views.ManageOIDCPublisherViews(project, request)
        assert view.manage_project_oidc_publishers_prefill() == {
            "disabled": {
                "GitHub": False,
                "GitLab": False,
                "Google": False,
                "ActiveState": False,
                "CircleCI": False,
            },
            "project": project,
            "github_publisher_form": view.github_publisher_form,
            "gitlab_publisher_form": view.gitlab_publisher_form,
            "google_publisher_form": view.google_publisher_form,
            "activestate_publisher_form": view.activestate_publisher_form,
            "circleci_publisher_form": view.circleci_publisher_form,
            "prefilled_provider": prefilled_data["provider"].lower(),
        }

        # The form data does not contain the provider, so we'll remove it from
        # the prefilled data before comparing them
        del prefilled_data["provider"]

        form = getattr(view, form_name)
        assert form.data == prefilled_data

    @pytest.mark.parametrize(
        ("missing_fields", "prefilled_data", "extra_fields"),
        [
            # Only some fields present
            (
                ["repository", "environment"],
                {
                    "provider": "github",
                    "owner": "owner",
                    "workflow_filename": "file.yml",
                },
                [],
            ),
            # Extra fields present
            (
                [],
                {
                    "provider": "github",
                    "owner": "owner",
                    "repository": "repo",
                    "workflow_filename": "file.yml",
                    "environment": "my_env",
                    "extra_field_1": "value1",
                    "extra_field_2": "value2",
                },
                ["extra_field_1", "extra_field_2"],
            ),
            # Both missing fields and extra fields present
            (
                ["owner", "repository"],
                {
                    "provider": "github",
                    "workflow_filename": "file.yml",
                    "environment": "my_env",
                    "extra_field_1": "value1",
                    "extra_field_2": "value2",
                },
                ["extra_field_1", "extra_field_2"],
            ),
        ],
    )
    def test_manage_project_oidc_publishers_prefill_partial(
        self, monkeypatch, missing_fields, prefilled_data, extra_fields
    ):
        project = pretend.stub(oidc_publishers=[], organization=None)
        request = pretend.stub(
            user=pretend.stub(),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                },
            ),
            find_service=lambda *a, **kw: None,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            POST=MultiDict(),
            params=MultiDict(prefilled_data),
        )

        view = oidc_views.ManageOIDCPublisherViews(project, request)
        assert view.manage_project_oidc_publishers_prefill() == {
            "disabled": {
                "GitHub": False,
                "GitLab": False,
                "Google": False,
                "ActiveState": False,
                "CircleCI": False,
            },
            "project": project,
            "github_publisher_form": view.github_publisher_form,
            "gitlab_publisher_form": view.gitlab_publisher_form,
            "google_publisher_form": view.google_publisher_form,
            "activestate_publisher_form": view.activestate_publisher_form,
            "circleci_publisher_form": view.circleci_publisher_form,
            "prefilled_provider": prefilled_data["provider"].lower(),
        }

        # The form data does not contain the provider, so we'll remove it from
        # the prefilled data before comparing them
        del prefilled_data["provider"]

        missing_data = {k: None for k in missing_fields}
        # The expected form data is the prefilled data plus the missing fields
        # (set to None) minus the extra fields
        expected_data = prefilled_data | missing_data
        expected_data = {
            k: v for k, v in expected_data.items() if k not in extra_fields
        }
        assert view.github_publisher_form.data == expected_data

    def test_manage_project_oidc_publishers_prefill_unknown_provider(self, monkeypatch):
        project = pretend.stub(oidc_publishers=[], organization=None)
        prefilled_data = {
            "provider": "github2",
            "owner": "owner",
            "repository": "repo",
            "workflow_filename": "file.yml",
            "environment": "my_env",
        }
        request = pretend.stub(
            user=pretend.stub(),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                },
            ),
            find_service=lambda *a, **kw: None,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            POST=MultiDict(),
            params=MultiDict(prefilled_data),
        )

        view = oidc_views.ManageOIDCPublisherViews(project, request)
        assert view.manage_project_oidc_publishers_prefill() == {
            "disabled": {
                "GitHub": False,
                "GitLab": False,
                "Google": False,
                "ActiveState": False,
                "CircleCI": False,
            },
            "project": project,
            "github_publisher_form": view.github_publisher_form,
            "gitlab_publisher_form": view.gitlab_publisher_form,
            "google_publisher_form": view.google_publisher_form,
            "activestate_publisher_form": view.activestate_publisher_form,
            "circleci_publisher_form": view.circleci_publisher_form,
            "prefilled_provider": None,
        }

        assert all(v is None for _, v in view.github_publisher_form.data.items())

    @pytest.mark.parametrize(
        ("publisher", "new_environment_name"),
        [
            (
                GitHubPublisher(
                    repository_name="some-repository",
                    repository_owner="some-owner",
                    repository_owner_id="666",
                    workflow_filename="some-workflow-filename.yml",
                    environment="",
                ),
                "fakeenv",
            ),
            (
                GitLabPublisher(
                    namespace="some-namespace",
                    project="some-project",
                    workflow_filepath="some-workflow-filename.yml",
                    environment="",
                    issuer_url="https://gitlab.com",
                ),
                "fakeenv",
            ),
        ],
    )
    def test_manage_project_oidc_publishers_constrain_environment(
        self,
        monkeypatch,
        metrics,
        db_request,
        publisher,
        new_environment_name,
    ):
        owner = UserFactory.create()
        db_request.user = owner

        project = ProjectFactory.create(oidc_publishers=[publisher])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)
        RoleFactory.create(user=owner, project=project, role_name="Owner")

        db_request.db.add(publisher)
        db_request.db.flush()  # To get the id

        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "constrained_publisher_id": str(publisher.id),
                "constrained_environment_name": new_environment_name,
            }
        )
        db_request.find_service = lambda *a, **kw: metrics
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request._ = lambda s: s
        view = oidc_views.ManageOIDCPublisherViews(project, db_request)

        assert isinstance(view.constrain_environment(), HTTPSeeOther)
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.constrain_publisher_environment.attempt",
            ),
        ]

        # The old publisher is actually removed entirely from the DB
        # and replaced by the new constrained publisher.
        publishers = db_request.db.query(OIDCPublisher).all()
        assert len(publishers) == 1
        constrained_publisher = publishers[0]
        assert constrained_publisher.environment == new_environment_name
        assert project.oidc_publishers == [constrained_publisher]

        assert project.record_event.calls == [
            pretend.call(
                tag=EventTag.Project.OIDCPublisherAdded,
                request=db_request,
                additional={
                    "publisher": constrained_publisher.publisher_name,
                    "id": str(constrained_publisher.id),
                    "specifier": str(constrained_publisher),
                    "url": publisher.publisher_url(),
                    "submitted_by": db_request.user.username,
                    "reified_from_pending_publisher": False,
                    "constrained_from_existing_publisher": True,
                },
            ),
            pretend.call(
                tag=EventTag.Project.OIDCPublisherRemoved,
                request=db_request,
                additional={
                    "publisher": publisher.publisher_name,
                    "id": str(publisher.id),
                    "specifier": str(publisher),
                    "url": publisher.publisher_url(),
                    "submitted_by": db_request.user.username,
                },
            ),
        ]
        assert db_request.flags.disallow_oidc.calls == [pretend.call()]
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Trusted publisher for project {project.name!r} has been "
                f"constrained to environment {new_environment_name!r}",
                queue="success",
            )
        ]

    def test_manage_project_oidc_publishers_constrain_environment_shared_publisher(
        self,
        metrics,
        db_request,
    ):
        publisher = GitHubPublisher(
            repository_name="some-repository",
            repository_owner="some-owner",
            repository_owner_id="666",
            workflow_filename="some-workflow-filename.yml",
            environment="",
        )
        owner = UserFactory.create()
        db_request.user = owner

        project = ProjectFactory.create(oidc_publishers=[publisher])
        other_project = ProjectFactory.create(oidc_publishers=[publisher])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)
        RoleFactory.create(user=owner, project=project, role_name="Owner")

        db_request.db.add(publisher)
        db_request.db.flush()  # To get the id

        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "constrained_publisher_id": str(publisher.id),
                "constrained_environment_name": "fakeenv",
            }
        )
        db_request.find_service = lambda *a, **kw: metrics
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request._ = lambda s: s
        view = oidc_views.ManageOIDCPublisherViews(project, db_request)

        assert isinstance(view.constrain_environment(), HTTPSeeOther)
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.constrain_publisher_environment.attempt",
            ),
        ]

        # The old publisher is should still be present in the DB, because other_project
        # still uses it.
        assert db_request.db.query(OIDCPublisher).count() == 2
        assert (
            db_request.db.query(GitHubPublisher)
            .filter(GitHubPublisher.environment == "")
            .filter(GitHubPublisher.projects.contains(other_project))
            .count()
        ) == 1

        # The new constrained publisher should exist, and associated to the current
        # project
        constrained_publisher = (
            db_request.db.query(GitHubPublisher)
            .filter(GitHubPublisher.environment == "fakeenv")
            .one()
        )
        assert project.oidc_publishers == [constrained_publisher]

        assert project.record_event.calls == [
            pretend.call(
                tag=EventTag.Project.OIDCPublisherAdded,
                request=db_request,
                additional={
                    "publisher": constrained_publisher.publisher_name,
                    "id": str(constrained_publisher.id),
                    "specifier": str(constrained_publisher),
                    "url": publisher.publisher_url(),
                    "submitted_by": db_request.user.username,
                    "reified_from_pending_publisher": False,
                    "constrained_from_existing_publisher": True,
                },
            ),
            pretend.call(
                tag=EventTag.Project.OIDCPublisherRemoved,
                request=db_request,
                additional={
                    "publisher": publisher.publisher_name,
                    "id": str(publisher.id),
                    "specifier": str(publisher),
                    "url": publisher.publisher_url(),
                    "submitted_by": db_request.user.username,
                },
            ),
        ]
        assert db_request.flags.disallow_oidc.calls == [pretend.call()]
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Trusted publisher for project {project.name!r} has been "
                f"constrained to environment 'fakeenv'",
                queue="success",
            )
        ]

    def test_constrain_oidc_publisher_admin_disabled(self, monkeypatch):
        project = pretend.stub(organization=None)
        request = pretend.stub(
            method="POST",
            params=MultiDict(),
            user=pretend.stub(),
            find_service=lambda *a, **kw: None,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: True)
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            _=lambda s: s,
            POST=MultiDict(
                {
                    "constrained_publisher_id": uuid.uuid4(),
                    "constrained_environment_name": "fakeenv",
                }
            ),
            registry=pretend.stub(settings={}),
        )

        view = oidc_views.ManageOIDCPublisherViews(project, request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            oidc_views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.constrain_environment() == default_response
        assert request.session.flash.calls == [
            pretend.call(
                (
                    "Trusted publishing is temporarily disabled. See "
                    "https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
        ]

    def test_constrain_oidc_publisher_invalid_params(self, monkeypatch, metrics):
        project = pretend.stub(organization=None)
        request = pretend.stub(
            method="POST",
            params=MultiDict(),
            user=pretend.stub(),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            _=lambda s: s,
            POST=MultiDict(
                {
                    "constrained_publisher_id": "not_an_uuid",
                    "constrained_environment_name": "fakeenv",
                }
            ),
            registry=pretend.stub(settings={}),
        )

        view = oidc_views.ManageOIDCPublisherViews(project, request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            oidc_views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.constrain_environment() == default_response
        assert view.metrics.increment.calls == [
            pretend.call("warehouse.oidc.constrain_publisher_environment.attempt")
        ]
        assert request.session.flash.calls == [
            pretend.call(
                "The trusted publisher could not be constrained",
                queue="error",
            )
        ]

    def test_constrain_non_extant_oidc_publisher(
        self, monkeypatch, metrics, db_request
    ):
        project = pretend.stub(organization=None)
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "constrained_publisher_id": str(uuid.uuid4()),
                "constrained_environment_name": "fakeenv",
            }
        )
        db_request.find_service = lambda *a, **kw: metrics
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )

        view = oidc_views.ManageOIDCPublisherViews(project, db_request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            oidc_views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.constrain_environment() == default_response
        assert view.metrics.increment.calls == [
            pretend.call("warehouse.oidc.constrain_publisher_environment.attempt")
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "Invalid publisher for project",
                queue="error",
            )
        ]

    def test_constrain_publisher_from_different_project(
        self, monkeypatch, metrics, db_request
    ):
        owner = UserFactory.create()
        db_request.user = owner

        publisher = GitHubPublisher(
            repository_name="some-repository",
            repository_owner="some-owner",
            repository_owner_id="666",
            workflow_filename="some-workflow-filename.yml",
            environment="",
        )

        request_project = ProjectFactory.create(oidc_publishers=[])
        request_project.record_event = pretend.call_recorder(lambda *a, **kw: None)
        RoleFactory.create(user=owner, project=request_project, role_name="Owner")

        ProjectFactory.create(oidc_publishers=[publisher])

        db_request.db.add(publisher)
        db_request.db.flush()  # To get the id

        db_request.params = MultiDict()
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "constrained_publisher_id": str(publisher.id),
                "constrained_environment_name": "fakeenv",
            }
        )
        db_request.find_service = lambda *a, **kw: metrics
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )

        view = oidc_views.ManageOIDCPublisherViews(request_project, db_request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            oidc_views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.constrain_environment() == default_response
        assert view.metrics.increment.calls == [
            pretend.call("warehouse.oidc.constrain_publisher_environment.attempt")
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "Invalid publisher for project",
                queue="error",
            )
        ]

    @pytest.mark.parametrize(
        "publisher",
        [
            ActiveStatePublisher(
                organization="some-org",
                activestate_project_name="some-project",
                actor="some-user",
                actor_id="some-user-id",
            ),
            GooglePublisher(
                email="some-email@example.com",
                sub="some-sub",
            ),
        ],
    )
    def test_constrain_unsupported_publisher(
        self, monkeypatch, metrics, db_request, publisher
    ):
        owner = UserFactory.create()
        db_request.user = owner
        db_request.db.add(publisher)
        db_request.db.flush()  # To get the id

        project = ProjectFactory.create(oidc_publishers=[publisher])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)
        RoleFactory.create(user=owner, project=project, role_name="Owner")

        db_request.params = MultiDict()
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "constrained_publisher_id": str(publisher.id),
                "constrained_environment_name": "fakeenv",
            }
        )
        db_request.find_service = lambda *a, **kw: metrics
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )

        view = oidc_views.ManageOIDCPublisherViews(project, db_request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            oidc_views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.constrain_environment() == default_response
        assert view.metrics.increment.calls == [
            pretend.call("warehouse.oidc.constrain_publisher_environment.attempt")
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "Can only constrain the environment for GitHub and GitLab publishers",
                queue="error",
            )
        ]

    def test_constrain_publisher_with_nonempty_environment(
        self, monkeypatch, metrics, db_request
    ):
        owner = UserFactory.create()
        db_request.user = owner

        publisher = GitHubPublisher(
            repository_name="some-repository",
            repository_owner="some-owner",
            repository_owner_id="666",
            workflow_filename="some-workflow-filename.yml",
            environment="env-already-constrained",
        )

        project = ProjectFactory.create(oidc_publishers=[publisher])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)
        RoleFactory.create(user=owner, project=project, role_name="Owner")

        db_request.db.add(publisher)
        db_request.db.flush()  # To get the id

        db_request.params = MultiDict()
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "constrained_publisher_id": str(publisher.id),
                "constrained_environment_name": "fakeenv",
            }
        )
        db_request.find_service = lambda *a, **kw: metrics
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )

        view = oidc_views.ManageOIDCPublisherViews(project, db_request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            oidc_views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.constrain_environment() == default_response
        assert view.metrics.increment.calls == [
            pretend.call("warehouse.oidc.constrain_publisher_environment.attempt")
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "Can only constrain the environment for publishers without an "
                "environment configured",
                queue="error",
            )
        ]

    @pytest.mark.parametrize(
        ("publisher_class", "publisher_kwargs"),
        [
            (
                GitHubPublisher,
                {
                    "repository_name": "some-repository",
                    "repository_owner": "some-owner",
                    "repository_owner_id": "666",
                    "workflow_filename": "some-workflow-filename.yml",
                },
            ),
            (
                GitLabPublisher,
                {
                    "namespace": "some-namespace",
                    "project": "some-project",
                    "workflow_filepath": "some-workflow-filename.yml",
                    "issuer_url": "https://gitlab.com",
                },
            ),
        ],
    )
    def test_constrain_environment_publisher_already_exists(
        self, monkeypatch, metrics, db_request, publisher_class, publisher_kwargs
    ):
        owner = UserFactory.create()
        db_request.user = owner

        # Create unconstrained and constrained versions of the publisher
        unconstrained = publisher_class(environment="", **publisher_kwargs)
        constrained = publisher_class(environment="fakeenv", **publisher_kwargs)

        project = ProjectFactory.create(oidc_publishers=[unconstrained, constrained])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)
        RoleFactory.create(user=owner, project=project, role_name="Owner")

        db_request.db.add_all([unconstrained, constrained])
        db_request.db.flush()  # To get the ids

        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "constrained_publisher_id": str(unconstrained.id),
                "constrained_environment_name": "fakeenv",
            }
        )
        db_request.find_service = lambda *a, **kw: metrics
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request._ = lambda s: s

        view = oidc_views.ManageOIDCPublisherViews(project, db_request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            oidc_views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.constrain_environment() == default_response
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.constrain_publisher_environment.attempt",
            ),
        ]
        assert project.record_event.calls == []
        assert db_request.session.flash.calls == [
            pretend.call(
                f"{unconstrained} is already registered with {project.name}",
                queue="error",
            )
        ]

    @pytest.mark.parametrize(
        ("view_name", "publisher", "make_form"),
        [
            (
                "add_github_oidc_publisher",
                pretend.stub(
                    id="fakeid",
                    publisher_name="GitHub",
                    repository_name="fakerepo",
                    publisher_url=(
                        lambda x=None: "https://github.com/fakeowner/fakerepo"
                    ),
                    owner="fakeowner",
                    owner_id="1234",
                    workflow_filename="fakeworkflow.yml",
                    environment="some-environment",
                ),
                lambda publisher: pretend.stub(
                    validate=pretend.call_recorder(lambda: True),
                    repository=pretend.stub(data=publisher.repository_name),
                    normalized_owner=publisher.owner,
                    workflow_filename=pretend.stub(data=publisher.workflow_filename),
                    normalized_environment=publisher.environment,
                ),
            ),
            (
                "add_gitlab_oidc_publisher",
                pretend.stub(
                    id="fakeid",
                    publisher_name="GitLab",
                    project="fakerepo",
                    publisher_url=(
                        lambda x=None: "https://gitlab.com/fakeowner/fakerepo"
                    ),
                    namespace="fakeowner",
                    workflow_filepath="subfolder/fakeworkflow.yml",
                    environment="some-environment",
                ),
                lambda publisher: pretend.stub(
                    validate=pretend.call_recorder(lambda: True),
                    project=pretend.stub(data=publisher.project),
                    namespace=pretend.stub(data=publisher.namespace),
                    workflow_filepath=pretend.stub(data=publisher.workflow_filepath),
                    normalized_environment=publisher.environment,
                    issuer_url=pretend.stub(data="https://gitlab.com"),
                ),
            ),
            (
                "add_google_oidc_publisher",
                pretend.stub(
                    id="fakeid",
                    publisher_name="Google",
                    publisher_url=lambda x=None: None,
                    email="some-environment@example.com",
                    sub="some-sub",
                ),
                lambda publisher: pretend.stub(
                    validate=pretend.call_recorder(lambda: True),
                    email=pretend.stub(data=publisher.email),
                    sub=pretend.stub(data=publisher.sub),
                ),
            ),
            (
                "add_activestate_oidc_publisher",
                pretend.stub(
                    id="fakeid",
                    publisher_name="ActiveState",
                    publisher_url=(
                        lambda x=None: "https://platform.activestate.com/some-org/some-project"  # noqa
                    ),
                    organization="some-org",
                    activestate_project_name="some-project",
                    actor="some-user",
                    actor_id="some-user-id",
                ),
                lambda publisher: pretend.stub(
                    validate=pretend.call_recorder(lambda: True),
                    organization=pretend.stub(data=publisher.organization),
                    project=pretend.stub(data=publisher.activestate_project_name),
                    actor=pretend.stub(data=publisher.actor),
                    actor_id="some-user-id",
                ),
            ),
        ],
    )
    def test_add_oidc_publisher_preexisting(
        self, metrics, monkeypatch, view_name, publisher, make_form
    ):
        # NOTE: Can't set __str__ using pretend.stub()
        monkeypatch.setattr(publisher.__class__, "__str__", lambda s: "fakespecifier")

        project = pretend.stub(
            name="fakeproject",
            oidc_publishers=[],
            organization=None,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
            users=[],
        )

        request = pretend.stub(
            user=pretend.stub(
                username="some-user",
            ),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                }
            ),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            POST=pretend.stub(),
            db=pretend.stub(
                query=lambda *a: pretend.stub(
                    filter=lambda *a: pretend.stub(one_or_none=lambda: publisher)
                ),
                add=pretend.call_recorder(lambda o: None),
            ),
            path="request-path",
        )

        publisher_form_obj = make_form(publisher)
        publisher_form_cls = pretend.call_recorder(lambda *a, **kw: publisher_form_obj)
        monkeypatch.setattr(oidc_views, "GitHubPublisherForm", publisher_form_cls)
        monkeypatch.setattr(oidc_views, "GitLabPublisherForm", publisher_form_cls)
        monkeypatch.setattr(oidc_views, "GooglePublisherForm", publisher_form_cls)
        monkeypatch.setattr(oidc_views, "ActiveStatePublisherForm", publisher_form_cls)
        monkeypatch.setattr(oidc_views, "CircleCIPublisherForm", publisher_form_cls)

        view = oidc_views.ManageOIDCPublisherViews(project, request)
        monkeypatch.setattr(
            view, "_hit_ratelimits", pretend.call_recorder(lambda: None)
        )
        monkeypatch.setattr(
            view, "_check_ratelimits", pretend.call_recorder(lambda: None)
        )

        assert isinstance(getattr(view, view_name)(), HTTPSeeOther)
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_publisher.attempt",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
            pretend.call(
                "warehouse.oidc.add_publisher.ok",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
        ]
        assert project.record_event.calls == [
            pretend.call(
                tag=EventTag.Project.OIDCPublisherAdded,
                request=request,
                additional={
                    "publisher": publisher.publisher_name,
                    "id": "fakeid",
                    "specifier": "fakespecifier",
                    "url": publisher.publisher_url(),
                    "submitted_by": "some-user",
                    "reified_from_pending_publisher": False,
                    "constrained_from_existing_publisher": False,
                },
            )
        ]
        assert request.session.flash.calls == [
            pretend.call(
                "Added fakespecifier "
                + (
                    f"in {publisher.publisher_url()}"
                    if publisher.publisher_url()
                    else ""
                )
                + " to fakeproject",
                queue="success",
            )
        ]
        assert request.db.add.calls == []
        assert publisher_form_obj.validate.calls == [pretend.call()]
        assert view._hit_ratelimits.calls == [pretend.call()]
        assert view._check_ratelimits.calls == [pretend.call()]
        assert project.oidc_publishers == [publisher]

    @pytest.mark.parametrize(
        ("view_name", "publisher_form_obj", "expected_publisher"),
        [
            (
                "add_github_oidc_publisher",
                pretend.stub(
                    validate=pretend.call_recorder(lambda: True),
                    repository=pretend.stub(data="fakerepo"),
                    normalized_owner="fakeowner",
                    workflow_filename=pretend.stub(data="fakeworkflow.yml"),
                    normalized_environment="some-environment",
                    owner_id="1234",
                ),
                pretend.stub(publisher_name="GitHub"),
            ),
            (
                "add_gitlab_oidc_publisher",
                pretend.stub(
                    validate=pretend.call_recorder(lambda: True),
                    project=pretend.stub(data="fakerepo"),
                    namespace=pretend.stub(data="fakeowner"),
                    workflow_filepath=pretend.stub(data="subfolder/fakeworkflow.yml"),
                    normalized_environment="some-environment",
                    issuer_url=pretend.stub(data="https://gitlab.com"),
                ),
                pretend.stub(publisher_name="GitLab"),
            ),
            (
                "add_google_oidc_publisher",
                pretend.stub(
                    validate=pretend.call_recorder(lambda: True),
                    email=pretend.stub(data="some-environment@example.com"),
                    sub=pretend.stub(data="some-sub"),
                ),
                "Google",
            ),
            (
                "add_activestate_oidc_publisher",
                pretend.stub(
                    validate=pretend.call_recorder(lambda: True),
                    id="fakeid",
                    publisher_name="ActiveState",
                    publisher_url=lambda x=None: None,
                    organization=pretend.stub(data="fake-org"),
                    project=pretend.stub(data="fake-project"),
                    actor=pretend.stub(data="fake-actor"),
                    actor_id="some-user-id",
                ),
                "ActiveState",
            ),
        ],
    )
    def test_add_oidc_publisher_created(
        self, metrics, monkeypatch, view_name, publisher_form_obj, expected_publisher
    ):
        fakeuser = pretend.stub()
        project = pretend.stub(
            name="fakeproject",
            oidc_publishers=[],
            organization=None,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
            users=[fakeuser],
        )

        request = pretend.stub(
            user=pretend.stub(
                username="some-user",
            ),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                }
            ),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            POST=pretend.stub(),
            db=pretend.stub(
                query=lambda *a: pretend.stub(
                    filter=lambda *a: pretend.stub(one_or_none=lambda: None)
                ),
                add=pretend.call_recorder(lambda o: setattr(o, "id", "fakeid")),
            ),
            path="request-path",
        )

        publisher_form_cls = pretend.call_recorder(lambda *a, **kw: publisher_form_obj)
        monkeypatch.setattr(oidc_views, "GitHubPublisherForm", publisher_form_cls)
        monkeypatch.setattr(oidc_views, "GitLabPublisherForm", publisher_form_cls)
        monkeypatch.setattr(oidc_views, "GooglePublisherForm", publisher_form_cls)
        monkeypatch.setattr(oidc_views, "ActiveStatePublisherForm", publisher_form_cls)
        monkeypatch.setattr(oidc_views, "CircleCIPublisherForm", publisher_form_cls)
        monkeypatch.setattr(
            oidc_views,
            "send_trusted_publisher_added_email",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        view = oidc_views.ManageOIDCPublisherViews(project, request)
        monkeypatch.setattr(
            view, "_hit_ratelimits", pretend.call_recorder(lambda: None)
        )
        monkeypatch.setattr(
            view, "_check_ratelimits", pretend.call_recorder(lambda: None)
        )

        assert isinstance(getattr(view, view_name)(), HTTPSeeOther)

        assert len(project.oidc_publishers) == 1
        publisher = project.oidc_publishers[0]

        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_publisher.attempt",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
            pretend.call(
                "warehouse.oidc.add_publisher.ok",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
        ]
        assert project.record_event.calls == [
            pretend.call(
                tag=EventTag.Project.OIDCPublisherAdded,
                request=request,
                additional={
                    "publisher": publisher.publisher_name,
                    "id": "fakeid",
                    "specifier": str(publisher),
                    "url": publisher.publisher_url(),
                    "submitted_by": "some-user",
                    "reified_from_pending_publisher": False,
                    "constrained_from_existing_publisher": False,
                },
            )
        ]
        assert request.session.flash.calls == [
            pretend.call(
                f"Added {str(publisher)} "
                + (
                    f"in {publisher.publisher_url()}"
                    if publisher.publisher_url()
                    else ""
                )
                + " to fakeproject",
                queue="success",
            )
        ]
        assert request.db.add.calls == [pretend.call(project.oidc_publishers[0])]
        assert publisher_form_obj.validate.calls == [pretend.call()]
        assert oidc_views.send_trusted_publisher_added_email.calls == [
            pretend.call(
                request,
                fakeuser,
                project_name="fakeproject",
                publisher=publisher,
            )
        ]
        assert view._hit_ratelimits.calls == [pretend.call()]
        assert view._check_ratelimits.calls == [pretend.call()]

    @pytest.mark.parametrize(
        ("view_name", "publisher_name", "publisher", "post_body"),
        [
            (
                "add_github_oidc_publisher",
                "GitHub",
                GitHubPublisher(
                    repository_name="some-repository",
                    repository_owner="some-owner",
                    repository_owner_id="666",
                    workflow_filename="some-workflow-filename.yml",
                    environment="some-environment",
                ),
                MultiDict(
                    {
                        "owner": "some-owner",
                        "repository": "some-repository",
                        "workflow_filename": "some-workflow-filename.yml",
                        "environment": "some-environment",
                    }
                ),
            ),
            (
                "add_gitlab_oidc_publisher",
                "GitLab",
                GitLabPublisher(
                    project="some-repository",
                    namespace="some-owner",
                    workflow_filepath="subfolder/some-workflow-filename.yml",
                    environment="some-environment",
                    issuer_url="https://gitlab.com",
                ),
                MultiDict(
                    {
                        "namespace": "some-owner",
                        "project": "some-repository",
                        "workflow_filepath": "subfolder/some-workflow-filename.yml",
                        "environment": "some-environment",
                        "issuer_url": "https://gitlab.com",
                    }
                ),
            ),
            (
                "add_google_oidc_publisher",
                "Google",
                GooglePublisher(
                    email="some-email@example.com",
                    sub="some-sub",
                ),
                MultiDict(
                    {
                        "email": "some-email@example.com",
                        "sub": "some-sub",
                    }
                ),
            ),
            (
                "add_activestate_oidc_publisher",
                "ActiveState",
                ActiveStatePublisher(
                    organization="some-org",
                    activestate_project_name="some-project",
                    actor="some-user",
                    actor_id="some-user-id",
                ),
                MultiDict(
                    {
                        "organization": "some-org",
                        "project": "some-project",
                        "actor": "some-user",
                    }
                ),
            ),
        ],
    )
    def test_add_oidc_publisher_already_registered_with_project(
        self, monkeypatch, db_request, view_name, publisher_name, publisher, post_body
    ):
        db_request.user = UserFactory.create()
        EmailFactory(user=db_request.user, verified=True, primary=True)
        db_request.db.add(publisher)
        db_request.db.flush()  # To get it in the DB

        project = pretend.stub(
            name="fakeproject",
            oidc_publishers=[publisher],
            organization=None,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )

        db_request.registry = pretend.stub(
            settings={
                "github.token": "fake-api-token",
            }
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = post_body

        view = oidc_views.ManageOIDCPublisherViews(project, db_request)
        monkeypatch.setattr(
            oidc_views.GitHubPublisherForm,
            "_lookup_owner",
            lambda *a: {"login": "some-owner", "id": "some-owner-id"},
        )

        monkeypatch.setattr(
            oidc_views.ActiveStatePublisherForm,
            "_lookup_organization",
            lambda *a: None,
        )

        monkeypatch.setattr(
            oidc_views.ActiveStatePublisherForm,
            "_lookup_actor",
            lambda *a: {"user_id": "some-user-id"},
        )

        monkeypatch.setattr(
            view, "_hit_ratelimits", pretend.call_recorder(lambda: None)
        )
        monkeypatch.setattr(
            view, "_check_ratelimits", pretend.call_recorder(lambda: None)
        )

        assert getattr(view, view_name)() == {
            "disabled": {
                "GitHub": False,
                "GitLab": False,
                "Google": False,
                "ActiveState": False,
                "CircleCI": False,
            },
            "project": project,
            "github_publisher_form": view.github_publisher_form,
            "gitlab_publisher_form": view.gitlab_publisher_form,
            "google_publisher_form": view.google_publisher_form,
            "activestate_publisher_form": view.activestate_publisher_form,
            "circleci_publisher_form": view.circleci_publisher_form,
            "prefilled_provider": view.prefilled_provider,
        }
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_publisher.attempt",
                tags=[f"publisher:{publisher_name}"],
            ),
        ]
        assert project.record_event.calls == []
        assert db_request.session.flash.calls == [
            pretend.call(
                f"{str(publisher)} is already registered with fakeproject",
                queue="error",
            )
        ]

    def test_add_oidc_publisher_already_registered_after_normalization(
        self, monkeypatch, db_request
    ):
        publisher = GitHubPublisher(
            repository_name="some-repository",
            repository_owner="some-owner",
            repository_owner_id="666",
            workflow_filename="some-workflow-filename.yml",
            environment="some-environment",
        )
        post_body = MultiDict(
            {
                "owner": "some-owner",
                "repository": "some-repository",
                "workflow_filename": "some-workflow-filename.yml",
                "environment": "SOME-environment",
            }
        )
        db_request.user = UserFactory.create()
        EmailFactory(user=db_request.user, verified=True, primary=True)
        db_request.db.add(publisher)
        db_request.db.flush()  # To get it in the DB

        project = pretend.stub(
            name="fakeproject",
            oidc_publishers=[publisher],
            organization=None,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )

        db_request.registry = pretend.stub(
            settings={
                "github.token": "fake-api-token",
            }
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = post_body

        view = oidc_views.ManageOIDCPublisherViews(project, db_request)
        monkeypatch.setattr(
            oidc_views.GitHubPublisherForm,
            "_lookup_owner",
            lambda *a: {"login": "some-owner", "id": "some-owner-id"},
        )

        monkeypatch.setattr(
            view, "_hit_ratelimits", pretend.call_recorder(lambda: None)
        )
        monkeypatch.setattr(
            view, "_check_ratelimits", pretend.call_recorder(lambda: None)
        )

        assert view.add_github_oidc_publisher() == {
            "disabled": {
                "GitHub": False,
                "GitLab": False,
                "Google": False,
                "ActiveState": False,
                "CircleCI": False,
            },
            "project": project,
            "github_publisher_form": view.github_publisher_form,
            "gitlab_publisher_form": view.gitlab_publisher_form,
            "google_publisher_form": view.google_publisher_form,
            "activestate_publisher_form": view.activestate_publisher_form,
            "circleci_publisher_form": view.circleci_publisher_form,
            "prefilled_provider": view.prefilled_provider,
        }
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_publisher.attempt",
                tags=["publisher:GitHub"],
            ),
        ]
        assert project.record_event.calls == []
        assert db_request.session.flash.calls == [
            pretend.call(
                f"{str(publisher)} is already registered with fakeproject",
                queue="error",
            )
        ]

    @pytest.mark.parametrize(
        ("view_name", "publisher_name"),
        [
            ("add_github_oidc_publisher", "GitHub"),
            ("add_gitlab_oidc_publisher", "GitLab"),
            ("add_google_oidc_publisher", "Google"),
            ("add_activestate_oidc_publisher", "ActiveState"),
        ],
    )
    def test_add_oidc_publisher_ratelimited(
        self, metrics, monkeypatch, view_name, publisher_name
    ):
        project = pretend.stub(organization=None)

        request = pretend.stub(
            user=pretend.stub(),
            registry=pretend.stub(settings={}),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            _=lambda s: s,
            POST=MultiDict(),
        )

        view = oidc_views.ManageOIDCPublisherViews(project, request)
        monkeypatch.setattr(
            view,
            "_check_ratelimits",
            pretend.call_recorder(
                pretend.raiser(
                    TooManyOIDCRegistrations(
                        resets_in=pretend.stub(total_seconds=lambda: 60)
                    )
                )
            ),
        )

        assert getattr(view, view_name)().__class__ == HTTPTooManyRequests
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_publisher.attempt",
                tags=[f"publisher:{publisher_name}"],
            ),
            pretend.call(
                "warehouse.oidc.add_publisher.ratelimited",
                tags=[f"publisher:{publisher_name}"],
            ),
        ]

    @pytest.mark.parametrize(
        ("view_name", "publisher_name"),
        [
            ("add_github_oidc_publisher", "GitHub"),
            ("add_gitlab_oidc_publisher", "GitLab"),
            ("add_google_oidc_publisher", "Google"),
            ("add_activestate_oidc_publisher", "ActiveState"),
        ],
    )
    def test_add_oidc_publisher_admin_disabled(
        self, monkeypatch, view_name, publisher_name
    ):
        project = pretend.stub(organization=None)
        request = pretend.stub(
            user=pretend.stub(),
            find_service=lambda *a, **kw: None,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: True)
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            _=lambda s: s,
            POST=MultiDict(),
            registry=pretend.stub(settings={}),
        )

        view = oidc_views.ManageOIDCPublisherViews(project, request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            oidc_views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert getattr(view, view_name)() == default_response
        assert request.session.flash.calls == [
            pretend.call(
                (
                    f"{publisher_name}-based trusted publishing is temporarily "
                    "disabled. See https://pypi.org/help#admin-intervention for "
                    "details."
                ),
                queue="error",
            )
        ]

    @pytest.mark.parametrize(
        ("view_name", "publisher_name"),
        [
            ("add_github_oidc_publisher", "GitHub"),
            ("add_gitlab_oidc_publisher", "GitLab"),
            ("add_google_oidc_publisher", "Google"),
            ("add_activestate_oidc_publisher", "ActiveState"),
        ],
    )
    def test_add_oidc_publisher_invalid_form(
        self, metrics, monkeypatch, view_name, publisher_name
    ):
        project = pretend.stub(organization=None)
        request = pretend.stub(
            user=pretend.stub(),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            _=lambda s: s,
            POST=MultiDict(),
            registry=pretend.stub(settings={}),
        )

        publisher_form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: False),
        )
        publisher_form_cls = pretend.call_recorder(lambda *a, **kw: publisher_form_obj)
        monkeypatch.setattr(oidc_views, "GitHubPublisherForm", publisher_form_cls)
        monkeypatch.setattr(oidc_views, "GitLabPublisherForm", publisher_form_cls)
        monkeypatch.setattr(oidc_views, "GooglePublisherForm", publisher_form_cls)
        monkeypatch.setattr(oidc_views, "ActiveStatePublisherForm", publisher_form_cls)

        view = oidc_views.ManageOIDCPublisherViews(project, request)
        default_response = {
            "github_publisher_form": publisher_form_obj,
            "gitlab_publisher_form": publisher_form_obj,
            "google_publisher_form": publisher_form_obj,
            "activestate_publisher_form": publisher_form_obj,
        }
        monkeypatch.setattr(
            oidc_views.ManageOIDCPublisherViews, "default_response", default_response
        )
        monkeypatch.setattr(
            view, "_check_ratelimits", pretend.call_recorder(lambda: None)
        )
        monkeypatch.setattr(
            view, "_hit_ratelimits", pretend.call_recorder(lambda: None)
        )

        assert getattr(view, view_name)() == default_response
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_publisher.attempt",
                tags=[f"publisher:{publisher_name}"],
            ),
        ]
        assert view._hit_ratelimits.calls == [pretend.call()]
        assert view._check_ratelimits.calls == [pretend.call()]
        assert publisher_form_obj.validate.calls == [pretend.call()]

    @pytest.mark.parametrize(
        "publisher",
        [
            GitHubPublisher(
                repository_name="some-repository",
                repository_owner="some-owner",
                repository_owner_id="666",
                workflow_filename="some-workflow-filename.yml",
                environment="some-environment",
            ),
            GitLabPublisher(
                project="some-repository",
                namespace="some-owner",
                workflow_filepath="subfolder/some-workflow-filename.yml",
                environment="some-environment",
                issuer_url="https://gitlab.com",
            ),
            GooglePublisher(
                email="some-email@example.com",
                sub="some-sub",
            ),
            ActiveStatePublisher(
                organization="some-org",
                activestate_project_name="some-project",
                actor="some-user",
                actor_id="some-user-id",
            ),
        ],
    )
    def test_delete_oidc_publisher_registered_to_multiple_projects(
        self, monkeypatch, db_request, publisher
    ):
        db_request.user = UserFactory.create()
        EmailFactory(user=db_request.user, verified=True, primary=True)
        db_request.db.add(publisher)
        db_request.db.flush()  # To get it in the DB

        project = ProjectFactory.create(oidc_publishers=[publisher])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)
        RoleFactory.create(user=db_request.user, project=project, role_name="Owner")
        another_project = ProjectFactory.create(oidc_publishers=[publisher])

        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = MultiDict(
            {
                "publisher_id": str(publisher.id),
            }
        )

        monkeypatch.setattr(
            oidc_views,
            "send_trusted_publisher_removed_email",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        view = oidc_views.ManageOIDCPublisherViews(project, db_request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            oidc_views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert isinstance(view.delete_oidc_publisher(), HTTPSeeOther)
        assert publisher not in project.oidc_publishers

        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.delete_publisher.attempt",
            ),
            pretend.call(
                "warehouse.oidc.delete_publisher.ok",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
        ]

        assert project.record_event.calls == [
            pretend.call(
                tag=EventTag.Project.OIDCPublisherRemoved,
                request=db_request,
                additional={
                    "publisher": publisher.publisher_name,
                    "id": str(publisher.id),
                    "specifier": str(publisher),
                    "url": publisher.publisher_url(),
                    "submitted_by": db_request.user.username,
                },
            )
        ]

        assert db_request.flags.disallow_oidc.calls == [pretend.call()]
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Removed trusted publisher for project {project.name!r}",
                queue="success",
            )
        ]

        # The publisher is not actually removed entirely from the DB, since it's
        # registered to other projects that haven't removed it.
        assert db_request.db.query(OIDCPublisher).one() == publisher
        assert another_project.oidc_publishers == [publisher]

        assert oidc_views.send_trusted_publisher_removed_email.calls == [
            pretend.call(
                db_request,
                db_request.user,
                project_name=project.name,
                publisher=publisher,
            )
        ]

    @pytest.mark.parametrize(
        "publisher",
        [
            GitHubPublisher(
                repository_name="some-repository",
                repository_owner="some-owner",
                repository_owner_id="666",
                workflow_filename="some-workflow-filename.yml",
                environment="some-environment",
            ),
            GitLabPublisher(
                project="some-repository",
                namespace="some-owner",
                workflow_filepath="subfolder/some-workflow-filename.yml",
                environment="some-environment",
                issuer_url="https://gitlab.com",
            ),
            GooglePublisher(
                email="some-email@example.com",
                sub="some-sub",
            ),
            ActiveStatePublisher(
                organization="some-org",
                activestate_project_name="some-project",
                actor="some-user",
                actor_id="some-user-id",
            ),
        ],
    )
    def test_delete_oidc_publisher_entirely(self, monkeypatch, db_request, publisher):
        db_request.user = UserFactory.create()
        EmailFactory(user=db_request.user, verified=True, primary=True)
        db_request.db.add(publisher)
        db_request.db.flush()  # To get it in the DB

        project = ProjectFactory.create(oidc_publishers=[publisher])
        RoleFactory.create(user=db_request.user, project=project, role_name="Owner")

        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = MultiDict(
            {
                "publisher_id": str(publisher.id),
            }
        )

        monkeypatch.setattr(
            oidc_views,
            "send_trusted_publisher_removed_email",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        view = oidc_views.ManageOIDCPublisherViews(project, db_request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            oidc_views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert isinstance(view.delete_oidc_publisher(), HTTPSeeOther)
        assert publisher not in project.oidc_publishers

        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.delete_publisher.attempt",
            ),
            pretend.call(
                "warehouse.oidc.delete_publisher.ok",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
        ]

        events = project.events.all()
        assert len(events) == 1
        event = events[0]
        assert event.tag == EventTag.Project.OIDCPublisherRemoved
        assert str(event.ip_address) == db_request.remote_addr
        assert event.additional == {
            "publisher": publisher.publisher_name,
            "id": str(publisher.id),
            "specifier": str(publisher),
            "url": publisher.publisher_url(),
            "submitted_by": db_request.user.username,
        }

        assert db_request.flags.disallow_oidc.calls == [pretend.call()]
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Removed trusted publisher for project {project.name!r}",
                queue="success",
            )
        ]

        # The publisher is actually removed entirely from the DB.
        assert db_request.db.query(OIDCPublisher).all() == []

        assert oidc_views.send_trusted_publisher_removed_email.calls == [
            pretend.call(
                db_request,
                db_request.user,
                project_name=project.name,
                publisher=publisher,
            )
        ]

    def test_delete_oidc_publisher_invalid_form(self, metrics, monkeypatch):
        publisher = pretend.stub()
        project = pretend.stub(oidc_publishers=[publisher], organization=None)
        request = pretend.stub(
            user=pretend.stub(),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            POST=MultiDict(),
            registry=pretend.stub(settings={}),
        )

        delete_publisher_form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: False),
        )
        delete_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: delete_publisher_form_obj
        )
        monkeypatch.setattr(
            oidc_views, "DeletePublisherForm", delete_publisher_form_cls
        )

        view = oidc_views.ManageOIDCPublisherViews(project, request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            oidc_views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.delete_oidc_publisher() == default_response
        assert len(project.oidc_publishers) == 1

        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.delete_publisher.attempt",
            ),
        ]

        assert delete_publisher_form_cls.calls == [pretend.call(request.POST)]
        assert delete_publisher_form_obj.validate.calls == [pretend.call()]

    @pytest.mark.parametrize(
        "other_publisher", [None, pretend.stub(id="different-fakeid")]
    )
    def test_delete_oidc_publisher_not_found(
        self, metrics, monkeypatch, other_publisher
    ):
        publisher = pretend.stub(
            publisher_name="fakepublisher",
            id="fakeid",
        )
        # NOTE: Can't set __str__ using pretend.stub()
        monkeypatch.setattr(publisher.__class__, "__str__", lambda s: "fakespecifier")

        project = pretend.stub(
            oidc_publishers=[publisher],
            organization=None,
            name="fakeproject",
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        request = pretend.stub(
            user=pretend.stub(),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            POST=MultiDict(),
            registry=pretend.stub(settings={}),
            db=pretend.stub(
                get=pretend.call_recorder(lambda *a, **kw: other_publisher),
            ),
            remote_addr="0.0.0.0",
        )

        delete_publisher_form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            publisher_id=pretend.stub(data="different-fakeid"),
        )
        delete_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: delete_publisher_form_obj
        )
        monkeypatch.setattr(
            oidc_views, "DeletePublisherForm", delete_publisher_form_cls
        )

        view = oidc_views.ManageOIDCPublisherViews(project, request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            oidc_views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.delete_oidc_publisher() == default_response
        assert publisher in project.oidc_publishers  # not deleted
        assert other_publisher not in project.oidc_publishers

        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.delete_publisher.attempt",
            ),
        ]

        assert project.record_event.calls == []
        assert request.session.flash.calls == [
            pretend.call("Invalid publisher for project", queue="error")
        ]

        assert delete_publisher_form_cls.calls == [pretend.call(request.POST)]
        assert delete_publisher_form_obj.validate.calls == [pretend.call()]

    def test_delete_oidc_publisher_admin_disabled(self, monkeypatch):
        project = pretend.stub(organization=None)
        request = pretend.stub(
            user=pretend.stub(),
            find_service=lambda *a, **kw: None,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: True)
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            POST=MultiDict(),
            registry=pretend.stub(settings={}),
        )

        view = oidc_views.ManageOIDCPublisherViews(project, request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            oidc_views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.delete_oidc_publisher() == default_response
        assert request.session.flash.calls == [
            pretend.call(
                (
                    "Trusted publishing is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
        ]
