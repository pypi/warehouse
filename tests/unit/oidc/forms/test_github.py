# SPDX-License-Identifier: Apache-2.0

import types

import pytest
import responses
import wtforms

from pyramid.i18n import Localizer
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

_LOOKUP_OWNER_URL = "https://api.github.com/users/some-owner"


class TestPendingGitHubPublisherForm:
    def test_validate(self, mocker, project_service):
        route_url = mocker.sentinel.route_url
        user = mocker.sentinel.user

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
            api_token=mocker.sentinel.api_token,
            route_url=route_url,
            check_project_name=project_service.check_project_name,
            user=user,
        )

        # We're testing only the basic validation here.
        owner_info = {"login": "fake-username", "id": "1234"}
        mocker.patch.object(form, "_lookup_owner", return_value=owner_info)

        assert form._check_project_name == project_service.check_project_name
        assert form._route_url == route_url
        assert form._user == user
        assert form.validate()

    def test_validate_project_name_already_in_use_owner(
        self, mocker, pyramid_config, project_service
    ):
        route_url = mocker.stub(name="route_url")
        route_url.return_value = ""

        user = UserFactory.create()
        project = ProjectFactory.create(name="some-project")
        RoleFactory.create(user=user, project=project)

        form = github.PendingGitHubPublisherForm(
            api_token="fake-token",
            route_url=route_url,
            check_project_name=project_service.check_project_name,
            user=user,
        )

        form.project_name.data = "some-project"
        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_project_name(form.project_name)

        # The project settings URL is only shown in the error message if
        # the user is the owner of the project
        route_url.assert_called_once_with(
            "manage.project.settings.publishing",
            project_name="some-project",
            _query={"project_name": "some-project", "provider": {"github"}},
        )

    def test_validate_project_name_already_in_use_not_owner(
        self, mocker, pyramid_config, project_service
    ):
        route_url = mocker.stub(name="route_url")
        route_url.return_value = ""

        user = UserFactory.create()
        ProjectFactory.create(name="some-project")

        form = github.PendingGitHubPublisherForm(
            api_token="fake-token",
            route_url=route_url,
            check_project_name=project_service.check_project_name,
            user=user,
        )

        form.project_name.data = "some-project"
        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_project_name(form.project_name)

        route_url.assert_not_called()

    @pytest.mark.parametrize(
        "reason",
        [
            ProjectNameUnavailableExistingError(
                types.SimpleNamespace(owners=[object()])
            ),
            ProjectNameUnavailableInvalidError(),
            ProjectNameUnavailableStdlibError(),
            ProjectNameUnavailableProhibitedError(),
            ProjectNameUnavailableSimilarError(similar_project_name="pkg_name"),
        ],
    )
    def test_validate_project_name_unavailable(self, reason, mocker, pyramid_config):
        def check_project_name(name):
            raise reason

        form = github.PendingGitHubPublisherForm(
            api_token="fake-token",
            route_url=mocker.stub(name="route_url"),
            check_project_name=check_project_name,
            user=mocker.sentinel.user,
        )

        form.project_name.data = "some-project"
        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_project_name(form.project_name)


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
    def test_validate(self, token, headers, mocker):
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
        mocker.patch.object(form, "_lookup_owner", return_value=owner_info)

        assert form._api_token == token
        assert form._headers_auth() == headers
        assert form.validate(), str(form.errors)

    @responses.activate
    def test_lookup_owner_404(self):
        responses.add(responses.GET, _LOOKUP_OWNER_URL, status=404)

        form = github.GitHubPublisherForm(api_token="fake-token")
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_owner("some-owner")

        assert len(responses.calls) == 1
        assert responses.calls[0].request.url == _LOOKUP_OWNER_URL
        assert responses.calls[0].request.headers["Authorization"] == "token fake-token"
        assert (
            responses.calls[0].request.headers["Accept"]
            == "application/vnd.github.v3+json"
        )
        assert responses.calls[0].request.req_kwargs["timeout"] == 5

    @responses.activate
    def test_lookup_owner_403(self, mocker):
        capture_message = mocker.patch.object(
            github.sentry_sdk, "capture_message", autospec=True
        )
        responses.add(
            responses.GET,
            _LOOKUP_OWNER_URL,
            status=403,
            json={"message": "fake-message"},
        )

        form = github.GitHubPublisherForm(api_token="fake-token")
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_owner("some-owner")

        assert len(responses.calls) == 1
        capture_message.assert_called_once_with(
            "Exceeded GitHub rate limit for user lookups. "
            "Reason: {'message': 'fake-message'}"
        )

    @responses.activate
    def test_lookup_owner_other_http_error(self, mocker):
        capture_message = mocker.patch.object(
            github.sentry_sdk, "capture_message", autospec=True
        )
        # anything that isn't 404 or 403
        responses.add(
            responses.GET, _LOOKUP_OWNER_URL, status=422, body=b"fake-content"
        )

        form = github.GitHubPublisherForm(api_token="fake-token")
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_owner("some-owner")

        assert len(responses.calls) == 1
        capture_message.assert_called_once_with(
            "Unexpected error from GitHub user lookup: response.content=b'fake-content'"
        )

    @responses.activate
    def test_lookup_owner_http_timeout(self, mocker):
        capture_message = mocker.patch.object(
            github.sentry_sdk, "capture_message", autospec=True
        )
        responses.add(responses.GET, _LOOKUP_OWNER_URL, body=github.requests.Timeout())

        form = github.GitHubPublisherForm(api_token="fake-token")
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_owner("some-owner")

        capture_message.assert_called_once_with(
            "Timeout from GitHub user lookup API (possibly offline)"
        )

    @responses.activate
    def test_lookup_owner_connection_error(self, mocker):
        capture_message = mocker.patch.object(
            github.sentry_sdk, "capture_message", autospec=True
        )
        responses.add(
            responses.GET, _LOOKUP_OWNER_URL, body=github.requests.ConnectionError()
        )

        form = github.GitHubPublisherForm(api_token="fake-token")
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_owner("some-owner")

        capture_message.assert_called_once_with(
            "Connection error from GitHub user lookup API (possibly offline)"
        )

    @responses.activate
    def test_lookup_owner_succeeds(self):
        owner_info = {"login": "fake-username", "id": 1234}
        responses.add(responses.GET, _LOOKUP_OWNER_URL, json=owner_info)

        form = github.GitHubPublisherForm(api_token="fake-token")
        info = form._lookup_owner("some-owner")

        assert len(responses.calls) == 1
        assert responses.calls[0].request.url == _LOOKUP_OWNER_URL
        assert responses.calls[0].request.headers["Authorization"] == "token fake-token"
        assert info == owner_info

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
    def test_validate_basic_invalid_fields(self, mocker, data):
        form = github.GitHubPublisherForm(
            MultiDict(data), api_token=mocker.sentinel.token
        )

        # We're testing only the basic validation here.
        owner_info = {"login": "fake-username", "id": "1234"}
        mocker.patch.object(form, "_lookup_owner", return_value=owner_info)

        assert not form.validate()

    def test_validate_owner(self, mocker):
        form = github.GitHubPublisherForm(api_token=mocker.sentinel.token)

        owner_info = {"login": "some-username", "id": "1234"}
        mocker.patch.object(form, "_lookup_owner", return_value=owner_info)

        form.owner.data = "SOME-USERNAME"
        form.validate_owner(form.owner)

        assert form.normalized_owner == "some-username"
        assert form.owner_id == "1234"

    def test_validate_workflow_filename_strips_whitespace(self, mocker):
        data = MultiDict(
            {
                "owner": "some-owner",
                "repository": "some-repo",
                "workflow_filename": "  some-workflow.yml  ",
            }
        )
        form = github.GitHubPublisherForm(
            MultiDict(data), api_token=mocker.sentinel.token
        )
        owner_info = {"login": "fake-username", "id": "1234"}
        mocker.patch.object(form, "_lookup_owner", return_value=owner_info)

        assert form.validate(), str(form.errors)
        assert form.owner.data == "some-owner"
        assert form.repository.data == "some-repo"
        assert form.workflow_filename.data == "some-workflow.yml"

    @pytest.mark.parametrize(
        "workflow_filename", ["missing_suffix", "/slash", "/many/slashes", "/slash.yml"]
    )
    def test_validate_workflow_filename_raises(self, mocker, workflow_filename):
        form = github.GitHubPublisherForm(api_token=mocker.sentinel.token)
        form.workflow_filename.data = workflow_filename

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_workflow_filename(form.workflow_filename)

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
    def test_validate_environment_raises(
        self, environment, expected, mocker, pyramid_request
    ):
        localizer = mocker.create_autospec(Localizer, instance=True)
        localizer.translate.side_effect = lambda ts: ts
        pyramid_request.localizer = localizer
        mocker.patch.object(
            i18n, "get_current_request", autospec=True, return_value=pyramid_request
        )

        form = github.GitHubPublisherForm(api_token=mocker.sentinel.token)
        form.environment.data = environment

        with pytest.raises(wtforms.validators.ValidationError) as e:
            form.validate_environment(form.environment)

        assert str(e.value).startswith(expected)

    @pytest.mark.parametrize("environment", ["", None])
    def test_validate_environment_passes(self, environment, mocker):
        form = github.GitHubPublisherForm(api_token=mocker.sentinel.token)
        form.environment.data = environment

        assert form.validate_environment(form.environment) is None

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
    def test_normalized_environment(self, data, expected, mocker):
        form = github.GitHubPublisherForm(
            api_token=mocker.sentinel.token, environment=data
        )
        assert form.normalized_environment == expected
