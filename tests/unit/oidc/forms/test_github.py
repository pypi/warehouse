# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest
import wtforms

from requests import ConnectionError, HTTPError, Timeout
from webob.multidict import MultiDict

from warehouse import i18n
from warehouse.oidc.forms import github
from warehouse.packaging.interfaces import (
    ProjectNameUnavailableExistingError,
    ProjectNameUnavailableInvalidError,
    ProjectNameUnavailableProhibitedError,
    ProjectNameUnavailableSimilarError,
    ProjectNameUnavailableStdlibError,
)

from ....common.db.accounts import UserFactory
from ....common.db.packaging import (
    ProjectFactory,
    RoleFactory,
)


class TestPendingGitHubPublisherForm:
    def test_validate(self, monkeypatch, project_service):
        route_url = pretend.stub()
        user = pretend.stub()

        data = MultiDict(
            {
                "owner": "some-owner",
                "repository": "some-repo",
                "workflow_filename": "some-workflow.yml",
                "project_name": "some-project",
            }
        )
        form = github.PendingGitHubPublisherForm(
            MultiDict(data),
            api_token=pretend.stub(),
            route_url=route_url,
            check_project_name=project_service.check_project_name,
            user=user,
        )

        # We're testing only the basic validation here.
        owner_info = {"login": "fake-username", "id": "1234"}
        monkeypatch.setattr(form, "_lookup_owner", lambda o: owner_info)

        assert form._check_project_name == project_service.check_project_name
        assert form._route_url == route_url
        assert form._user == user
        assert form.validate()

    def test_validate_project_name_already_in_use_owner(
        self, pyramid_config, project_service
    ):
        route_url = pretend.call_recorder(lambda *args, **kwargs: "")

        user = UserFactory.create()
        project = ProjectFactory.create(name="some-project")
        RoleFactory.create(user=user, project=project)

        form = github.PendingGitHubPublisherForm(
            api_token="fake-token",
            route_url=route_url,
            check_project_name=project_service.check_project_name,
            user=user,
        )

        field = pretend.stub(data="some-project")
        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_project_name(field)

        # The project settings URL is only shown in the error message if
        # the user is the owner of the project
        assert route_url.calls == [
            pretend.call(
                "manage.project.settings.publishing",
                project_name="some-project",
                _query={"provider": {"github"}},
            )
        ]

    def test_validate_project_name_already_in_use_not_owner(
        self, pyramid_config, project_service
    ):
        route_url = pretend.call_recorder(lambda *args, **kwargs: "")

        user = UserFactory.create()
        ProjectFactory.create(name="some-project")

        form = github.PendingGitHubPublisherForm(
            api_token="fake-token",
            route_url=route_url,
            check_project_name=project_service.check_project_name,
            user=user,
        )

        field = pretend.stub(data="some-project")
        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_project_name(field)

        assert route_url.calls == []

    @pytest.mark.parametrize(
        "reason",
        [
            ProjectNameUnavailableExistingError(pretend.stub(owners=[pretend.stub()])),
            ProjectNameUnavailableInvalidError(),
            ProjectNameUnavailableStdlibError(),
            ProjectNameUnavailableProhibitedError(),
            ProjectNameUnavailableSimilarError(similar_project_name="pkg_name"),
        ],
    )
    def test_validate_project_name_unavailable(self, reason, pyramid_config):
        def check_project_name(name):
            raise reason

        form = github.PendingGitHubPublisherForm(
            api_token="fake-token",
            route_url=pretend.call_recorder(lambda *args, **kwargs: ""),
            check_project_name=check_project_name,
            user=pretend.stub(),
        )

        field = pretend.stub(data="some-project")
        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_project_name(field)


class TestGitHubPublisherForm:
    @pytest.mark.parametrize(
        ("token", "headers"),
        [
            (
                None,
                {},
            ),
            ("fake-token", {"Authorization": "token fake-token"}),
        ],
    )
    def test_validate(self, token, headers, monkeypatch):
        data = MultiDict(
            {
                "owner": "some-owner",
                "repository": "some-repo",
                "workflow_filename": "some-workflow.yml",
            }
        )
        form = github.GitHubPublisherForm(MultiDict(data), api_token=token)

        # We're testing only the basic validation here.
        owner_info = {"login": "fake-username", "id": "1234"}
        monkeypatch.setattr(form, "_lookup_owner", lambda o: owner_info)

        assert form._api_token == token
        assert form._headers_auth() == headers
        assert form.validate(), str(form.errors)

    def test_lookup_owner_404(self, monkeypatch):
        response = pretend.stub(
            status_code=404, raise_for_status=pretend.raiser(HTTPError)
        )
        requests = pretend.stub(
            get=pretend.call_recorder(lambda o, **kw: response), HTTPError=HTTPError
        )
        monkeypatch.setattr(github, "requests", requests)

        form = github.GitHubPublisherForm(api_token="fake-token")
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_owner("some-owner")

        assert requests.get.calls == [
            pretend.call(
                "https://api.github.com/users/some-owner",
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "Authorization": "token fake-token",
                },
                allow_redirects=True,
                timeout=5,
            )
        ]

    def test_lookup_owner_403(self, monkeypatch):
        response = pretend.stub(
            status_code=403,
            raise_for_status=pretend.raiser(HTTPError),
            json=lambda: {"message": "fake-message"},
        )
        requests = pretend.stub(
            get=pretend.call_recorder(lambda o, **kw: response), HTTPError=HTTPError
        )
        monkeypatch.setattr(github, "requests", requests)

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(github, "sentry_sdk", sentry_sdk)

        form = github.GitHubPublisherForm(api_token="fake-token")
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_owner("some-owner")

        assert requests.get.calls == [
            pretend.call(
                "https://api.github.com/users/some-owner",
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "Authorization": "token fake-token",
                },
                allow_redirects=True,
                timeout=5,
            )
        ]
        assert sentry_sdk.capture_message.calls == [
            pretend.call(
                "Exceeded GitHub rate limit for user lookups. "
                "Reason: {'message': 'fake-message'}"
            )
        ]

    def test_lookup_owner_other_http_error(self, monkeypatch):
        response = pretend.stub(
            # anything that isn't 404 or 403
            status_code=422,
            raise_for_status=pretend.raiser(HTTPError),
            content=b"fake-content",
        )
        requests = pretend.stub(
            get=pretend.call_recorder(lambda o, **kw: response), HTTPError=HTTPError
        )
        monkeypatch.setattr(github, "requests", requests)

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(github, "sentry_sdk", sentry_sdk)

        form = github.GitHubPublisherForm(api_token="fake-token")
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_owner("some-owner")

        assert requests.get.calls == [
            pretend.call(
                "https://api.github.com/users/some-owner",
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "Authorization": "token fake-token",
                },
                allow_redirects=True,
                timeout=5,
            )
        ]

        assert sentry_sdk.capture_message.calls == [
            pretend.call(
                "Unexpected error from GitHub user lookup: "
                "response.content=b'fake-content'"
            )
        ]

    def test_lookup_owner_http_timeout(self, monkeypatch):
        requests = pretend.stub(
            get=pretend.raiser(Timeout),
            Timeout=Timeout,
            HTTPError=HTTPError,
            ConnectionError=ConnectionError,
        )
        monkeypatch.setattr(github, "requests", requests)

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(github, "sentry_sdk", sentry_sdk)

        form = github.GitHubPublisherForm(api_token="fake-token")
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_owner("some-owner")

        assert sentry_sdk.capture_message.calls == [
            pretend.call("Timeout from GitHub user lookup API (possibly offline)")
        ]

    def test_lookup_owner_connection_error(self, monkeypatch):
        requests = pretend.stub(
            get=pretend.raiser(ConnectionError),
            Timeout=Timeout,
            HTTPError=HTTPError,
            ConnectionError=ConnectionError,
        )
        monkeypatch.setattr(github, "requests", requests)

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(github, "sentry_sdk", sentry_sdk)

        form = github.GitHubPublisherForm(api_token="fake-token")
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_owner("some-owner")

        assert sentry_sdk.capture_message.calls == [
            pretend.call(
                "Connection error from GitHub user lookup API (possibly offline)"
            )
        ]

    def test_lookup_owner_succeeds(self, monkeypatch):
        fake_owner_info = pretend.stub()
        response = pretend.stub(
            status_code=200,
            raise_for_status=pretend.call_recorder(lambda: None),
            json=lambda: fake_owner_info,
        )
        requests = pretend.stub(
            get=pretend.call_recorder(lambda o, **kw: response), HTTPError=HTTPError
        )
        monkeypatch.setattr(github, "requests", requests)

        form = github.GitHubPublisherForm(api_token="fake-token")
        info = form._lookup_owner("some-owner")

        assert requests.get.calls == [
            pretend.call(
                "https://api.github.com/users/some-owner",
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "Authorization": "token fake-token",
                },
                allow_redirects=True,
                timeout=5,
            )
        ]
        assert response.raise_for_status.calls == [pretend.call()]
        assert info == fake_owner_info

    @pytest.mark.parametrize(
        "data",
        [
            {"owner": None, "repository": "some", "workflow_filename": "some"},
            {"owner": "", "repository": "some", "workflow_filename": "some"},
            {
                "owner": "invalid_characters@",
                "repository": "some",
                "workflow_filename": "some",
            },
            {"repository": None, "owner": "some", "workflow_filename": "some"},
            {"repository": "", "owner": "some", "workflow_filename": "some"},
            {
                "repository": "$invalid#characters",
                "owner": "some",
                "workflow_filename": "some",
            },
            {"repository": "some", "owner": "some", "workflow_filename": None},
            {"repository": "some", "owner": "some", "workflow_filename": ""},
        ],
    )
    def test_validate_basic_invalid_fields(self, monkeypatch, data):
        form = github.GitHubPublisherForm(MultiDict(data), api_token=pretend.stub())

        # We're testing only the basic validation here.
        owner_info = {"login": "fake-username", "id": "1234"}
        monkeypatch.setattr(form, "_lookup_owner", lambda o: owner_info)

        assert not form.validate()

    def test_validate_owner(self, monkeypatch):
        form = github.GitHubPublisherForm(api_token=pretend.stub())

        owner_info = {"login": "some-username", "id": "1234"}
        monkeypatch.setattr(form, "_lookup_owner", lambda o: owner_info)

        field = pretend.stub(data="SOME-USERNAME")
        form.validate_owner(field)

        assert form.normalized_owner == "some-username"
        assert form.owner_id == "1234"

    @pytest.mark.parametrize(
        "workflow_filename", ["missing_suffix", "/slash", "/many/slashes", "/slash.yml"]
    )
    def test_validate_workflow_filename(self, workflow_filename):
        form = github.GitHubPublisherForm(api_token=pretend.stub())
        field = pretend.stub(data=workflow_filename)

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_workflow_filename(field)

    @pytest.mark.parametrize(
        ("environment", "expected"),
        [
            ("f" * 256, "Environment name is too long"),
            (" foo", "Environment name may not start with whitespace"),
            ("foo ", "Environment name may not end with whitespace"),
            ("'", "Environment name must not contain non-printable characters"),
            ('"', "Environment name must not contain non-printable characters"),
            ("`", "Environment name must not contain non-printable characters"),
            (",", "Environment name must not contain non-printable characters"),
            (";", "Environment name must not contain non-printable characters"),
            ("\\", "Environment name must not contain non-printable characters"),
            ("\x00", "Environment name must not contain non-printable characters"),
            ("\x1f", "Environment name must not contain non-printable characters"),
            ("\x7f", "Environment name must not contain non-printable characters"),
            ("\t", "Environment name must not contain non-printable characters"),
            ("\r", "Environment name must not contain non-printable characters"),
            ("\n", "Environment name must not contain non-printable characters"),
        ],
    )
    def test_validate_environment_raises(self, environment, expected, monkeypatch):
        request = pretend.stub(
            localizer=pretend.stub(translate=pretend.call_recorder(lambda ts: ts))
        )
        get_current_request = pretend.call_recorder(lambda: request)
        monkeypatch.setattr(i18n, "get_current_request", get_current_request)

        form = github.GitHubPublisherForm(api_token=pretend.stub())
        field = pretend.stub(data=environment)

        with pytest.raises(wtforms.validators.ValidationError) as e:
            form.validate_environment(field)

        assert str(e.value).startswith(expected)

    @pytest.mark.parametrize("environment", ["", None])
    def test_validate_environment_passes(self, environment):
        field = pretend.stub(data=environment)
        form = github.GitHubPublisherForm(api_token=pretend.stub())

        assert form.validate_environment(field) is None

    @pytest.mark.parametrize(
        ("data", "expected"),
        [
            ("wu-tang", "wu-tang"),  # Non-alpha characters are preserved
            ("WU-TANG", "wu-tang"),  # Alpha characters are lowercased
            ("Foo   Bar", "foo   bar"),  # Whitespace is preserved
            ("", ""),  # Empty string is empty string
            (None, ""),  # None and empty string are equivalent
        ],
    )
    def test_normalized_environment(self, data, expected):
        form = github.GitHubPublisherForm(api_token=pretend.stub(), environment=data)
        assert form.normalized_environment == expected
