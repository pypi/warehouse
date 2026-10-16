# SPDX-License-Identifier: Apache-2.0

import datetime
import uuid

import pytest

from pyramid.httpexceptions import HTTPSeeOther, HTTPTooManyRequests
from sqlalchemy import select
from webob.multidict import MultiDict

from tests.common.db.accounts import UserFactory
from tests.common.db.oidc import (
    ActiveStatePublisherFactory,
    GitHubPublisherFactory,
    GitLabPublisherFactory,
    GooglePublisherFactory,
)
from tests.common.db.packaging import ProjectFactory, RoleFactory
from warehouse.admin.flags import AdminFlag, AdminFlagValue
from warehouse.events.tags import EventTag
from warehouse.manage.views import oidc_publishers as oidc_views
from warehouse.metrics import IMetricsService
from warehouse.oidc.interfaces import TooManyOIDCRegistrations
from warehouse.oidc.models import GitHubPublisher, OIDCPublisher
from warehouse.packaging.models import Project
from warehouse.rate_limiting import DummyRateLimiter, IRateLimiter, RateLimiter

PROVIDER_FLAGS = {
    "GitHub": AdminFlagValue.DISALLOW_GITHUB_OIDC,
    "GitLab": AdminFlagValue.DISALLOW_GITLAB_OIDC,
    "Google": AdminFlagValue.DISALLOW_GOOGLE_OIDC,
    "ActiveState": AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC,
}

ADD_VIEWS = [
    pytest.param("add_github_oidc_publisher", "GitHub", id="GitHub"),
    pytest.param("add_gitlab_oidc_publisher", "GitLab", id="GitLab"),
    pytest.param("add_google_oidc_publisher", "Google", id="Google"),
    pytest.param("add_activestate_oidc_publisher", "ActiveState", id="ActiveState"),
]

# Each provider's add view, a factory for the publisher it registers, its
# columns, and the POST body that the real form turns into that publisher (with
# the lookups in `form_lookups`).
ADD_PUBLISHERS = [
    pytest.param(
        "add_github_oidc_publisher",
        GitHubPublisherFactory,
        {
            "repository_name": "some-repository",
            "repository_owner": "some-owner",
            "repository_owner_id": "some-owner-id",
            "workflow_filename": "some-workflow-filename.yml",
            "environment": "some-environment",
        },
        {
            "owner": "some-owner",
            "repository": "some-repository",
            "workflow_filename": "some-workflow-filename.yml",
            "environment": "some-environment",
        },
        id="GitHub",
    ),
    pytest.param(
        "add_gitlab_oidc_publisher",
        GitLabPublisherFactory,
        {
            "namespace": "some-owner",
            "project": "some-repository",
            "workflow_filepath": "subfolder/some-workflow-filename.yml",
            "environment": "some-environment",
            "issuer_url": "https://gitlab.com",
        },
        {
            "namespace": "some-owner",
            "project": "some-repository",
            "workflow_filepath": "subfolder/some-workflow-filename.yml",
            "environment": "some-environment",
            "issuer_url": "https://gitlab.com",
        },
        id="GitLab",
    ),
    pytest.param(
        "add_google_oidc_publisher",
        GooglePublisherFactory,
        {"email": "some-email@example.com", "sub": "some-sub"},
        {"email": "some-email@example.com", "sub": "some-sub"},
        id="Google",
    ),
    pytest.param(
        "add_activestate_oidc_publisher",
        ActiveStatePublisherFactory,
        {
            "organization": "some-org",
            "activestate_project_name": "some-project",
            "actor": "some-user",
            "actor_id": "some-user-id",
        },
        {"organization": "some-org", "project": "some-project", "actor": "some-user"},
        id="ActiveState",
    ),
]

ALL_PUBLISHER_FACTORIES = [
    pytest.param(GitHubPublisherFactory, id="GitHub"),
    pytest.param(GitLabPublisherFactory, id="GitLab"),
    pytest.param(GooglePublisherFactory, id="Google"),
    pytest.param(ActiveStatePublisherFactory, id="ActiveState"),
]


def _added_flash(publisher, project):
    url = publisher.publisher_url()
    return f"Added {publisher} " + (f"in {url}" if url else "") + f" to {project.name}"


def _events(project: Project) -> dict[str, dict | None]:
    """
    Project events keyed by tag. Events recorded in one transaction share a
    timestamp, so their order is not meaningful. Each tag must appear once.
    """
    events = project.events.all()
    by_tag = {event.tag: event.additional for event in events}
    assert len(by_tag) == len(events), "duplicate event tags"
    return by_tag


class TestManageOIDCPublisherViews:
    @pytest.fixture
    def oidc_limiters(self, mocker):
        """Spied per-user and per-IP OIDC registration rate limiters."""
        limiters = {"user": DummyRateLimiter(), "ip": DummyRateLimiter()}
        for limiter in limiters.values():
            mocker.spy(limiter, "test")
            mocker.spy(limiter, "hit")
        return limiters

    @pytest.fixture
    def publishing_request(self, db_request, pyramid_services, oidc_limiters, mocker):
        """
        A POST-less request from a user with a verified primary email, with every
        trusted publishing provider enabled and the OIDC registration rate
        limiters backed by ``oidc_limiters``.
        """
        db_request.user = UserFactory.create(with_verified_primary_email=True)
        db_request.registry.settings = {"github.token": "fake-api-token"}
        db_request.POST = MultiDict()
        db_request.path = "request-path"
        for flag in (AdminFlagValue.DISALLOW_OIDC, *PROVIDER_FLAGS.values()):
            db_request.db.get(AdminFlag, flag.value).enabled = False
        mocker.spy(db_request.flags, "disallow_oidc")
        mocker.spy(db_request.session, "flash")
        for key in ("user", "ip"):
            pyramid_services.register_service(
                oidc_limiters[key],
                IRateLimiter,
                None,
                name=f"{key}_oidc.publisher.register",
            )
        return db_request

    @pytest.fixture
    def form_lookups(self, mocker):
        """Stub the GitHub and ActiveState API lookups the real forms make."""
        mocker.patch.object(
            oidc_views.GitHubPublisherForm,
            "_lookup_owner",
            autospec=True,
            return_value={"login": "some-owner", "id": "some-owner-id"},
        )
        mocker.patch.object(
            oidc_views.ActiveStatePublisherForm,
            "_lookup_organization",
            autospec=True,
            return_value=None,
        )
        mocker.patch.object(
            oidc_views.ActiveStatePublisherForm,
            "_lookup_actor",
            autospec=True,
            return_value={"user_id": "some-user-id"},
        )

    @pytest.fixture
    def send_added_email(self, mocker):
        return mocker.patch.object(
            oidc_views, "send_trusted_publisher_added_email", autospec=True
        )

    @pytest.fixture
    def send_removed_email(self, mocker):
        return mocker.patch.object(
            oidc_views, "send_trusted_publisher_removed_email", autospec=True
        )

    @staticmethod
    def _enable_flag(request, flag):
        request.db.get(AdminFlag, flag.value).enabled = True

    @staticmethod
    def _default_response(view, disabled=(), prefilled_provider=None):
        return {
            "disabled": {name: name in disabled for name in PROVIDER_FLAGS},
            "project": view.project,
            "github_publisher_form": view.github_publisher_form,
            "gitlab_publisher_form": view.gitlab_publisher_form,
            "google_publisher_form": view.google_publisher_form,
            "activestate_publisher_form": view.activestate_publisher_form,
            "prefilled_provider": prefilled_provider,
        }

    def test_initializes(self, publishing_request, metrics, mocker):
        mocker.spy(publishing_request, "find_service")
        project = ProjectFactory.create()

        view = oidc_views.ManageOIDCPublisherViews(project, publishing_request)

        assert view.project is project
        assert view.request is publishing_request
        assert view.metrics is metrics
        publishing_request.find_service.assert_called_once_with(
            IMetricsService, context=None
        )

    @pytest.mark.parametrize(
        ("ip_exceeded", "user_exceeded"),
        [
            (False, False),
            (False, True),
            (True, False),
            (True, True),
        ],
    )
    def test_ratelimiting(
        self, publishing_request, pyramid_services, mocker, ip_exceeded, user_exceeded
    ):
        user_rate_limiter = mocker.create_autospec(RateLimiter, instance=True)
        user_rate_limiter.test.return_value = not user_exceeded
        user_rate_limiter.resets_in.return_value = datetime.timedelta(seconds=60)
        ip_rate_limiter = mocker.create_autospec(RateLimiter, instance=True)
        ip_rate_limiter.test.return_value = not ip_exceeded
        ip_rate_limiter.resets_in.return_value = datetime.timedelta(seconds=30)
        pyramid_services.register_service(
            user_rate_limiter, IRateLimiter, None, name="user_oidc.publisher.register"
        )
        pyramid_services.register_service(
            ip_rate_limiter, IRateLimiter, None, name="ip_oidc.publisher.register"
        )
        mocker.spy(publishing_request, "find_service")

        view = oidc_views.ManageOIDCPublisherViews(
            ProjectFactory.create(), publishing_request
        )

        assert view._ratelimiters == {
            "user.oidc": user_rate_limiter,
            "ip.oidc": ip_rate_limiter,
        }
        assert publishing_request.find_service.call_args_list == [
            mocker.call(IMetricsService, context=None),
            mocker.call(IRateLimiter, name="user_oidc.publisher.register"),
            mocker.call(IRateLimiter, name="ip_oidc.publisher.register"),
        ]

        view._hit_ratelimits()

        user_rate_limiter.hit.assert_called_once_with(publishing_request.user.id)
        ip_rate_limiter.hit.assert_called_once_with(publishing_request.remote_addr)

        if user_exceeded or ip_exceeded:
            with pytest.raises(TooManyOIDCRegistrations) as excinfo:
                view._check_ratelimits()
            assert excinfo.value.resets_in == datetime.timedelta(
                seconds=60 if user_exceeded else 30
            )
        else:
            view._check_ratelimits()

    def test_manage_project_oidc_publishers(self, publishing_request, mocker):
        view = oidc_views.ManageOIDCPublisherViews(
            ProjectFactory.create(), publishing_request
        )

        assert view.manage_project_oidc_publishers() == self._default_response(view)
        assert publishing_request.flags.disallow_oidc.call_args_list == [
            mocker.call(),
            mocker.call(AdminFlagValue.DISALLOW_GITHUB_OIDC),
            mocker.call(AdminFlagValue.DISALLOW_GITLAB_OIDC),
            mocker.call(AdminFlagValue.DISALLOW_GOOGLE_OIDC),
            mocker.call(AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC),
        ]
        publishing_request.session.flash.assert_not_called()

    def test_manage_project_oidc_publishers_admin_disabled(
        self, publishing_request, mocker
    ):
        self._enable_flag(publishing_request, AdminFlagValue.DISALLOW_OIDC)

        view = oidc_views.ManageOIDCPublisherViews(
            ProjectFactory.create(), publishing_request
        )

        assert view.manage_project_oidc_publishers() == self._default_response(
            view, disabled=PROVIDER_FLAGS
        )
        assert publishing_request.flags.disallow_oidc.call_args_list == [
            mocker.call(),
            mocker.call(AdminFlagValue.DISALLOW_GITHUB_OIDC),
            mocker.call(AdminFlagValue.DISALLOW_GITLAB_OIDC),
            mocker.call(AdminFlagValue.DISALLOW_GOOGLE_OIDC),
            mocker.call(AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC),
        ]
        publishing_request.session.flash.assert_called_once_with(
            (
                "Trusted publishing is temporarily disabled. "
                "See https://pypi.org/help#admin-intervention for details."
            ),
            queue="error",
        )

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
        self, publishing_request, form_name, prefilled_data
    ):
        publishing_request.params = MultiDict(prefilled_data)

        view = oidc_views.ManageOIDCPublisherViews(
            ProjectFactory.create(), publishing_request
        )

        assert view.manage_project_oidc_publishers_prefill() == self._default_response(
            view, prefilled_provider=prefilled_data["provider"].lower()
        )
        # The form data does not contain the provider
        expected_data = {k: v for k, v in prefilled_data.items() if k != "provider"}
        assert getattr(view, form_name).data == expected_data

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
        self, publishing_request, missing_fields, prefilled_data, extra_fields
    ):
        publishing_request.params = MultiDict(prefilled_data)

        view = oidc_views.ManageOIDCPublisherViews(
            ProjectFactory.create(), publishing_request
        )

        assert view.manage_project_oidc_publishers_prefill() == self._default_response(
            view, prefilled_provider=prefilled_data["provider"].lower()
        )
        # The expected form data is the prefilled data, without the provider and
        # the extra fields, plus the missing fields set to None.
        expected_data = {
            k: v
            for k, v in (prefilled_data | dict.fromkeys(missing_fields)).items()
            if k != "provider" and k not in extra_fields
        }
        assert view.github_publisher_form.data == expected_data

    def test_manage_project_oidc_publishers_prefill_unknown_provider(
        self, publishing_request
    ):
        publishing_request.params = MultiDict(
            {
                "provider": "github2",
                "owner": "owner",
                "repository": "repo",
                "workflow_filename": "file.yml",
                "environment": "my_env",
            }
        )

        view = oidc_views.ManageOIDCPublisherViews(
            ProjectFactory.create(), publishing_request
        )

        assert view.manage_project_oidc_publishers_prefill() == self._default_response(
            view
        )
        assert all(v is None for v in view.github_publisher_form.data.values())

    @pytest.fixture
    def constrain_request(self, publishing_request):
        """Build a constrain-environment POST for a publisher id."""

        def _make(publisher_id, environment="fakeenv"):
            publishing_request.POST = MultiDict(
                {
                    "constrained_publisher_id": str(publisher_id),
                    "constrained_environment_name": environment,
                }
            )
            return publishing_request

        return _make

    @pytest.mark.parametrize(
        "publisher_factory",
        [
            pytest.param(GitHubPublisherFactory, id="GitHub"),
            pytest.param(GitLabPublisherFactory, id="GitLab"),
        ],
    )
    def test_manage_project_oidc_publishers_constrain_environment(
        self, constrain_request, metrics, publisher_factory
    ):
        publisher = publisher_factory.create(environment="")
        project = ProjectFactory.create(oidc_publishers=[publisher])
        request = constrain_request(publisher.id)

        view = oidc_views.ManageOIDCPublisherViews(project, request)

        response = view.constrain_environment()
        assert isinstance(response, HTTPSeeOther)
        assert response.location == request.path
        metrics.increment.assert_called_once_with(
            "warehouse.oidc.constrain_publisher_environment.attempt"
        )

        # The old publisher is removed entirely from the DB and replaced by the
        # new constrained publisher.
        constrained_publisher = request.db.scalars(select(OIDCPublisher)).one()
        assert constrained_publisher.environment == "fakeenv"
        assert project.oidc_publishers == [constrained_publisher]

        assert _events(project) == {
            EventTag.Project.OIDCPublisherAdded: {
                "publisher": constrained_publisher.publisher_name,
                "id": str(constrained_publisher.id),
                "specifier": str(constrained_publisher),
                "url": constrained_publisher.publisher_url(),
                "submitted_by": request.user.username,
                "reified_from_pending_publisher": False,
                "constrained_from_existing_publisher": True,
            },
            EventTag.Project.OIDCPublisherRemoved: {
                "publisher": publisher.publisher_name,
                "id": str(publisher.id),
                "specifier": str(publisher),
                "url": publisher.publisher_url(),
                "submitted_by": request.user.username,
            },
        }
        request.flags.disallow_oidc.assert_called_once_with()
        request.session.flash.assert_called_once_with(
            f"Trusted publisher for project {project.name!r} has been "
            f"constrained to environment 'fakeenv'",
            queue="success",
        )

    def test_manage_project_oidc_publishers_constrain_environment_shared_publisher(
        self, constrain_request, metrics
    ):
        publisher = GitHubPublisherFactory.create(environment="")
        project = ProjectFactory.create(oidc_publishers=[publisher])
        other_project = ProjectFactory.create(oidc_publishers=[publisher])
        request = constrain_request(publisher.id)

        view = oidc_views.ManageOIDCPublisherViews(project, request)

        response = view.constrain_environment()
        assert isinstance(response, HTTPSeeOther)
        assert response.location == request.path
        metrics.increment.assert_called_once_with(
            "warehouse.oidc.constrain_publisher_environment.attempt"
        )

        # The new constrained publisher exists and belongs to the current project.
        constrained_publisher = request.db.scalars(
            select(GitHubPublisher).where(GitHubPublisher.environment == "fakeenv")
        ).one()
        assert project.oidc_publishers == [constrained_publisher]

        # The old publisher stays in the DB, because other_project still uses it.
        assert set(request.db.scalars(select(OIDCPublisher))) == {
            publisher,
            constrained_publisher,
        }
        assert other_project.oidc_publishers == [publisher]

        assert _events(project) == {
            EventTag.Project.OIDCPublisherAdded: {
                "publisher": constrained_publisher.publisher_name,
                "id": str(constrained_publisher.id),
                "specifier": str(constrained_publisher),
                "url": constrained_publisher.publisher_url(),
                "submitted_by": request.user.username,
                "reified_from_pending_publisher": False,
                "constrained_from_existing_publisher": True,
            },
            EventTag.Project.OIDCPublisherRemoved: {
                "publisher": publisher.publisher_name,
                "id": str(publisher.id),
                "specifier": str(publisher),
                "url": publisher.publisher_url(),
                "submitted_by": request.user.username,
            },
        }
        request.flags.disallow_oidc.assert_called_once_with()
        request.session.flash.assert_called_once_with(
            f"Trusted publisher for project {project.name!r} has been "
            f"constrained to environment 'fakeenv'",
            queue="success",
        )

    def test_constrain_oidc_publisher_admin_disabled(self, constrain_request, metrics):
        request = constrain_request(uuid.uuid4())
        self._enable_flag(request, AdminFlagValue.DISALLOW_OIDC)

        view = oidc_views.ManageOIDCPublisherViews(ProjectFactory.create(), request)

        assert view.constrain_environment() == self._default_response(
            view, disabled=PROVIDER_FLAGS
        )
        metrics.increment.assert_not_called()
        request.session.flash.assert_called_once_with(
            (
                "Trusted publishing is temporarily disabled. See "
                "https://pypi.org/help#admin-intervention for details."
            ),
            queue="error",
        )

    def test_constrain_oidc_publisher_invalid_params(self, constrain_request, metrics):
        request = constrain_request("not_an_uuid")

        view = oidc_views.ManageOIDCPublisherViews(ProjectFactory.create(), request)

        assert view.constrain_environment() == self._default_response(view)
        metrics.increment.assert_called_once_with(
            "warehouse.oidc.constrain_publisher_environment.attempt"
        )
        request.session.flash.assert_called_once_with(
            "The trusted publisher could not be constrained", queue="error"
        )

    def test_constrain_non_extant_oidc_publisher(self, constrain_request, metrics):
        request = constrain_request(uuid.uuid4())

        view = oidc_views.ManageOIDCPublisherViews(ProjectFactory.create(), request)

        assert view.constrain_environment() == self._default_response(view)
        metrics.increment.assert_called_once_with(
            "warehouse.oidc.constrain_publisher_environment.attempt"
        )
        request.session.flash.assert_called_once_with(
            "Invalid publisher for project", queue="error"
        )

    def test_constrain_publisher_from_different_project(
        self, constrain_request, metrics
    ):
        publisher = GitHubPublisherFactory.create(environment="")
        ProjectFactory.create(oidc_publishers=[publisher])
        project = ProjectFactory.create()
        request = constrain_request(publisher.id)

        view = oidc_views.ManageOIDCPublisherViews(project, request)

        assert view.constrain_environment() == self._default_response(view)
        metrics.increment.assert_called_once_with(
            "warehouse.oidc.constrain_publisher_environment.attempt"
        )
        request.session.flash.assert_called_once_with(
            "Invalid publisher for project", queue="error"
        )

    @pytest.mark.parametrize(
        "publisher_factory",
        [
            pytest.param(ActiveStatePublisherFactory, id="ActiveState"),
            pytest.param(GooglePublisherFactory, id="Google"),
        ],
    )
    def test_constrain_unsupported_publisher(
        self, constrain_request, metrics, publisher_factory
    ):
        publisher = publisher_factory.create()
        project = ProjectFactory.create(oidc_publishers=[publisher])
        request = constrain_request(publisher.id)

        view = oidc_views.ManageOIDCPublisherViews(project, request)

        assert view.constrain_environment() == self._default_response(view)
        metrics.increment.assert_called_once_with(
            "warehouse.oidc.constrain_publisher_environment.attempt"
        )
        request.session.flash.assert_called_once_with(
            "Can only constrain the environment for GitHub and GitLab publishers",
            queue="error",
        )

    def test_constrain_publisher_with_nonempty_environment(
        self, constrain_request, metrics
    ):
        publisher = GitHubPublisherFactory.create(environment="env-already-constrained")
        project = ProjectFactory.create(oidc_publishers=[publisher])
        request = constrain_request(publisher.id)

        view = oidc_views.ManageOIDCPublisherViews(project, request)

        assert view.constrain_environment() == self._default_response(view)
        metrics.increment.assert_called_once_with(
            "warehouse.oidc.constrain_publisher_environment.attempt"
        )
        request.session.flash.assert_called_once_with(
            "Can only constrain the environment for publishers without an "
            "environment configured",
            queue="error",
        )

    @pytest.mark.parametrize(
        ("publisher_factory", "publisher_kwargs"),
        [
            pytest.param(
                GitHubPublisherFactory,
                {
                    "repository_name": "some-repository",
                    "repository_owner": "some-owner",
                    "repository_owner_id": "666",
                    "workflow_filename": "some-workflow-filename.yml",
                },
                id="GitHub",
            ),
            pytest.param(
                GitLabPublisherFactory,
                {
                    "namespace": "some-namespace",
                    "project": "some-project",
                    "workflow_filepath": "some-workflow-filename.yml",
                    "issuer_url": "https://gitlab.com",
                },
                id="GitLab",
            ),
        ],
    )
    def test_constrain_environment_publisher_already_exists(
        self, constrain_request, metrics, publisher_factory, publisher_kwargs
    ):
        unconstrained = publisher_factory.create(environment="", **publisher_kwargs)
        constrained = publisher_factory.create(
            environment="fakeenv", **publisher_kwargs
        )
        project = ProjectFactory.create(oidc_publishers=[unconstrained, constrained])
        request = constrain_request(unconstrained.id)

        view = oidc_views.ManageOIDCPublisherViews(project, request)

        assert view.constrain_environment() == self._default_response(view)
        metrics.increment.assert_called_once_with(
            "warehouse.oidc.constrain_publisher_environment.attempt"
        )
        assert _events(project) == {}
        request.session.flash.assert_called_once_with(
            f"{unconstrained} is already registered with {project.name}",
            queue="error",
        )

    @pytest.mark.usefixtures("form_lookups")
    @pytest.mark.parametrize(
        ("view_name", "publisher_factory", "publisher_kwargs", "post_body"),
        ADD_PUBLISHERS,
    )
    def test_add_oidc_publisher_preexisting(
        self,
        publishing_request,
        oidc_limiters,
        send_added_email,
        metrics,
        mocker,
        view_name,
        publisher_factory,
        publisher_kwargs,
        post_body,
    ):
        publisher = publisher_factory.create(**publisher_kwargs)
        project = ProjectFactory.create()
        owner = RoleFactory.create(project=project, role_name="Owner").user
        publishing_request.POST = MultiDict(post_body)

        view = oidc_views.ManageOIDCPublisherViews(project, publishing_request)

        assert isinstance(getattr(view, view_name)(), HTTPSeeOther)

        # The existing publisher is reused, not duplicated.
        assert publishing_request.db.scalars(select(OIDCPublisher)).all() == [publisher]
        assert project.oidc_publishers == [publisher]
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.oidc.add_publisher.attempt",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
            mocker.call(
                "warehouse.oidc.add_publisher.ok",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
        ]
        assert _events(project) == {
            EventTag.Project.OIDCPublisherAdded: {
                "publisher": publisher.publisher_name,
                "id": str(publisher.id),
                "specifier": str(publisher),
                "url": publisher.publisher_url(),
                "submitted_by": publishing_request.user.username,
                "reified_from_pending_publisher": False,
                "constrained_from_existing_publisher": False,
            }
        }
        publishing_request.session.flash.assert_called_once_with(
            _added_flash(publisher, project), queue="success"
        )
        send_added_email.assert_called_once_with(
            publishing_request, owner, project_name=project.name, publisher=publisher
        )
        oidc_limiters["user"].test.assert_called_once_with(publishing_request.user.id)
        oidc_limiters["ip"].hit.assert_called_once_with(publishing_request.remote_addr)

    @pytest.mark.usefixtures("form_lookups")
    @pytest.mark.parametrize(
        ("view_name", "publisher_factory", "publisher_kwargs", "post_body"),
        ADD_PUBLISHERS,
    )
    def test_add_oidc_publisher_created(
        self,
        publishing_request,
        oidc_limiters,
        send_added_email,
        metrics,
        mocker,
        view_name,
        publisher_factory,
        publisher_kwargs,
        post_body,
    ):
        project = ProjectFactory.create()
        owner = RoleFactory.create(project=project, role_name="Owner").user
        publishing_request.POST = MultiDict(post_body)

        view = oidc_views.ManageOIDCPublisherViews(project, publishing_request)

        assert isinstance(getattr(view, view_name)(), HTTPSeeOther)

        publisher = publishing_request.db.scalars(select(OIDCPublisher)).one()
        assert isinstance(publisher, publisher_factory._meta.model)
        for column, value in publisher_kwargs.items():
            assert getattr(publisher, column) == value
        assert project.oidc_publishers == [publisher]
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.oidc.add_publisher.attempt",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
            mocker.call(
                "warehouse.oidc.add_publisher.ok",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
        ]
        assert _events(project) == {
            EventTag.Project.OIDCPublisherAdded: {
                "publisher": publisher.publisher_name,
                "id": str(publisher.id),
                "specifier": str(publisher),
                "url": publisher.publisher_url(),
                "submitted_by": publishing_request.user.username,
                "reified_from_pending_publisher": False,
                "constrained_from_existing_publisher": False,
            }
        }
        publishing_request.session.flash.assert_called_once_with(
            _added_flash(publisher, project), queue="success"
        )
        send_added_email.assert_called_once_with(
            publishing_request, owner, project_name=project.name, publisher=publisher
        )
        oidc_limiters["user"].test.assert_called_once_with(publishing_request.user.id)
        oidc_limiters["ip"].hit.assert_called_once_with(publishing_request.remote_addr)

    @pytest.mark.usefixtures("form_lookups")
    @pytest.mark.parametrize(
        ("view_name", "publisher_factory", "publisher_kwargs", "post_body"),
        ADD_PUBLISHERS,
    )
    def test_add_oidc_publisher_already_registered_with_project(
        self,
        publishing_request,
        send_added_email,
        metrics,
        view_name,
        publisher_factory,
        publisher_kwargs,
        post_body,
    ):
        publisher = publisher_factory.create(**publisher_kwargs)
        project = ProjectFactory.create(oidc_publishers=[publisher])
        RoleFactory.create(project=project, role_name="Owner")
        publishing_request.POST = MultiDict(post_body)

        view = oidc_views.ManageOIDCPublisherViews(project, publishing_request)

        assert getattr(view, view_name)() == self._default_response(view)
        metrics.increment.assert_called_once_with(
            "warehouse.oidc.add_publisher.attempt",
            tags=[f"publisher:{publisher.publisher_name}"],
        )
        assert _events(project) == {}
        send_added_email.assert_not_called()
        publishing_request.session.flash.assert_called_once_with(
            f"{publisher} is already registered with {project.name}",
            queue="error",
        )

    @pytest.mark.usefixtures("form_lookups")
    def test_add_oidc_publisher_already_registered_after_normalization(
        self, publishing_request, metrics
    ):
        publisher = GitHubPublisherFactory.create(
            repository_name="some-repository",
            repository_owner="some-owner",
            workflow_filename="some-workflow-filename.yml",
            environment="some-environment",
        )
        project = ProjectFactory.create(oidc_publishers=[publisher])
        publishing_request.POST = MultiDict(
            {
                "owner": "some-owner",
                "repository": "some-repository",
                "workflow_filename": "some-workflow-filename.yml",
                "environment": "SOME-environment",
            }
        )

        view = oidc_views.ManageOIDCPublisherViews(project, publishing_request)

        assert view.add_github_oidc_publisher() == self._default_response(view)
        metrics.increment.assert_called_once_with(
            "warehouse.oidc.add_publisher.attempt", tags=["publisher:GitHub"]
        )
        assert _events(project) == {}
        publishing_request.session.flash.assert_called_once_with(
            f"{publisher} is already registered with {project.name}",
            queue="error",
        )

    @pytest.mark.parametrize(("view_name", "publisher_name"), ADD_VIEWS)
    def test_add_oidc_publisher_ratelimited(
        self,
        publishing_request,
        pyramid_services,
        metrics,
        mocker,
        view_name,
        publisher_name,
    ):
        user_rate_limiter = mocker.create_autospec(RateLimiter, instance=True)
        user_rate_limiter.test.return_value = False
        user_rate_limiter.resets_in.return_value = datetime.timedelta(seconds=60)
        pyramid_services.register_service(
            user_rate_limiter, IRateLimiter, None, name="user_oidc.publisher.register"
        )

        view = oidc_views.ManageOIDCPublisherViews(
            ProjectFactory.create(), publishing_request
        )

        response = getattr(view, view_name)()

        assert isinstance(response, HTTPTooManyRequests)
        assert response.headers["Retry-After"] == "60"
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.oidc.add_publisher.attempt",
                tags=[f"publisher:{publisher_name}"],
            ),
            mocker.call(
                "warehouse.oidc.add_publisher.ratelimited",
                tags=[f"publisher:{publisher_name}"],
            ),
        ]
        user_rate_limiter.hit.assert_not_called()

    @pytest.mark.parametrize(("view_name", "publisher_name"), ADD_VIEWS)
    def test_add_oidc_publisher_admin_disabled(
        self, publishing_request, metrics, view_name, publisher_name
    ):
        self._enable_flag(publishing_request, PROVIDER_FLAGS[publisher_name])

        view = oidc_views.ManageOIDCPublisherViews(
            ProjectFactory.create(), publishing_request
        )

        assert getattr(view, view_name)() == self._default_response(
            view, disabled=[publisher_name]
        )
        metrics.increment.assert_not_called()
        publishing_request.session.flash.assert_called_once_with(
            (
                f"{publisher_name}-based trusted publishing is temporarily "
                "disabled. See https://pypi.org/help#admin-intervention for "
                "details."
            ),
            queue="error",
        )

    @pytest.mark.parametrize(("view_name", "publisher_name"), ADD_VIEWS)
    def test_add_oidc_publisher_invalid_form(
        self, publishing_request, oidc_limiters, metrics, view_name, publisher_name
    ):
        project = ProjectFactory.create()

        view = oidc_views.ManageOIDCPublisherViews(project, publishing_request)

        assert getattr(view, view_name)() == self._default_response(view)
        assert project.oidc_publishers == []
        metrics.increment.assert_called_once_with(
            "warehouse.oidc.add_publisher.attempt",
            tags=[f"publisher:{publisher_name}"],
        )
        oidc_limiters["user"].test.assert_called_once_with(publishing_request.user.id)
        oidc_limiters["ip"].hit.assert_called_once_with(publishing_request.remote_addr)
        publishing_request.session.flash.assert_called_once_with(
            "The trusted publisher could not be registered", queue="error"
        )

    @pytest.fixture
    def delete_request(self, publishing_request):
        """Build a delete-publisher POST for a publisher id."""

        def _make(publisher_id):
            publishing_request.POST = MultiDict({"publisher_id": str(publisher_id)})
            return publishing_request

        return _make

    @pytest.mark.parametrize("publisher_factory", ALL_PUBLISHER_FACTORIES)
    def test_delete_oidc_publisher_registered_to_multiple_projects(
        self, delete_request, send_removed_email, metrics, mocker, publisher_factory
    ):
        publisher = publisher_factory.create()
        project = ProjectFactory.create(oidc_publishers=[publisher])
        owner = RoleFactory.create(project=project, role_name="Owner").user
        another_project = ProjectFactory.create(oidc_publishers=[publisher])
        request = delete_request(publisher.id)

        view = oidc_views.ManageOIDCPublisherViews(project, request)

        assert isinstance(view.delete_oidc_publisher(), HTTPSeeOther)
        assert project.oidc_publishers == []
        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.oidc.delete_publisher.attempt"),
            mocker.call(
                "warehouse.oidc.delete_publisher.ok",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
        ]
        assert _events(project) == {
            EventTag.Project.OIDCPublisherRemoved: {
                "publisher": publisher.publisher_name,
                "id": str(publisher.id),
                "specifier": str(publisher),
                "url": publisher.publisher_url(),
                "submitted_by": request.user.username,
            }
        }
        request.flags.disallow_oidc.assert_called_once_with()
        request.session.flash.assert_called_once_with(
            f"Removed trusted publisher for project {project.name!r}",
            queue="success",
        )

        # The publisher stays in the DB, since another project still uses it.
        assert request.db.scalars(select(OIDCPublisher)).one() == publisher
        assert another_project.oidc_publishers == [publisher]

        send_removed_email.assert_called_once_with(
            request, owner, project_name=project.name, publisher=publisher
        )

    @pytest.mark.parametrize("publisher_factory", ALL_PUBLISHER_FACTORIES)
    def test_delete_oidc_publisher_entirely(
        self, delete_request, send_removed_email, metrics, mocker, publisher_factory
    ):
        publisher = publisher_factory.create()
        project = ProjectFactory.create(oidc_publishers=[publisher])
        owner = RoleFactory.create(project=project, role_name="Owner").user
        request = delete_request(publisher.id)

        view = oidc_views.ManageOIDCPublisherViews(project, request)

        assert isinstance(view.delete_oidc_publisher(), HTTPSeeOther)
        assert project.oidc_publishers == []
        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.oidc.delete_publisher.attempt"),
            mocker.call(
                "warehouse.oidc.delete_publisher.ok",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
        ]

        events = project.events.all()
        assert len(events) == 1
        event = events[0]
        assert event.tag == EventTag.Project.OIDCPublisherRemoved
        assert str(event.ip_address) == request.remote_addr
        assert event.additional == {
            "publisher": publisher.publisher_name,
            "id": str(publisher.id),
            "specifier": str(publisher),
            "url": publisher.publisher_url(),
            "submitted_by": request.user.username,
        }

        request.flags.disallow_oidc.assert_called_once_with()
        request.session.flash.assert_called_once_with(
            f"Removed trusted publisher for project {project.name!r}",
            queue="success",
        )

        # The publisher is removed entirely from the DB.
        assert request.db.scalars(select(OIDCPublisher)).all() == []

        send_removed_email.assert_called_once_with(
            request, owner, project_name=project.name, publisher=publisher
        )

    def test_delete_oidc_publisher_invalid_form(self, publishing_request, metrics):
        publisher = GitHubPublisherFactory.create()
        project = ProjectFactory.create(oidc_publishers=[publisher])

        view = oidc_views.ManageOIDCPublisherViews(project, publishing_request)

        assert view.delete_oidc_publisher() == self._default_response(view)
        assert project.oidc_publishers == [publisher]
        metrics.increment.assert_called_once_with(
            "warehouse.oidc.delete_publisher.attempt"
        )
        publishing_request.session.flash.assert_not_called()

    @pytest.mark.parametrize("other_project", [False, True])
    def test_delete_oidc_publisher_not_found(
        self, delete_request, send_removed_email, metrics, other_project
    ):
        publisher = GitHubPublisherFactory.create()
        project = ProjectFactory.create(oidc_publishers=[publisher])
        RoleFactory.create(project=project, role_name="Owner")
        if other_project:
            # A real publisher, registered to some other project.
            other_publisher = GitHubPublisherFactory.create()
            ProjectFactory.create(oidc_publishers=[other_publisher])
            other_publisher_id = other_publisher.id
        else:
            other_publisher_id = uuid.uuid4()
        request = delete_request(other_publisher_id)

        view = oidc_views.ManageOIDCPublisherViews(project, request)

        assert view.delete_oidc_publisher() == self._default_response(view)
        assert project.oidc_publishers == [publisher]
        metrics.increment.assert_called_once_with(
            "warehouse.oidc.delete_publisher.attempt"
        )
        assert _events(project) == {}
        send_removed_email.assert_not_called()
        request.session.flash.assert_called_once_with(
            "Invalid publisher for project", queue="error"
        )

    def test_delete_oidc_publisher_admin_disabled(self, delete_request, metrics):
        request = delete_request(uuid.uuid4())
        self._enable_flag(request, AdminFlagValue.DISALLOW_OIDC)

        view = oidc_views.ManageOIDCPublisherViews(ProjectFactory.create(), request)

        assert view.delete_oidc_publisher() == self._default_response(
            view, disabled=PROVIDER_FLAGS
        )
        metrics.increment.assert_not_called()
        request.session.flash.assert_called_once_with(
            (
                "Trusted publishing is temporarily disabled. "
                "See https://pypi.org/help#admin-intervention for details."
            ),
            queue="error",
        )
