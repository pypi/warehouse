# SPDX-License-Identifier: Apache-2.0

import types

import pytest
import wtforms

from requests import ConnectionError as RequestsConnectionError, HTTPError, Timeout
from requests.exceptions import JSONDecodeError
from webob.multidict import MultiDict

from warehouse.oidc.forms import circleci
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

PROJECT_UUID = "00000000-0000-1000-8000-000000000002"


class TestPendingCircleCIPublisherForm:
    def test_validate(self, mocker, project_service):
        route_url = mocker.sentinel.route_url

        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
                "project_name": "some-project",
            }
        )
        form = circleci.PendingCircleCIPublisherForm(
            MultiDict(data),
            route_url=route_url,
            check_project_name=project_service.check_project_name,
            user=mocker.sentinel.user,
        )
        mocker.patch.object(form, "_lookup_project_metadata", return_value=None)

        assert form._check_project_name == project_service.check_project_name
        assert form._route_url == route_url
        assert form.validate()

    def test_validate_project_name_already_in_use_owner(
        self, mocker, pyramid_config, project_service
    ):
        route_url = mocker.stub(name="route_url")
        route_url.return_value = ""

        user = UserFactory.create()
        project = ProjectFactory.create(name="some-project")
        RoleFactory.create(user=user, project=project)

        form = circleci.PendingCircleCIPublisherForm(
            route_url=route_url,
            check_project_name=project_service.check_project_name,
            user=user,
        )

        field = mocker.Mock(data="some-project")
        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_project_name(field)

        # The project settings URL is only shown in the error message if
        # the user is the owner of the project
        route_url.assert_called_once_with(
            "manage.project.settings.publishing",
            project_name="some-project",
            _query={"provider": {"circleci"}},
        )

    def test_validate_project_name_already_in_use_not_owner(
        self, mocker, pyramid_config, project_service
    ):
        route_url = mocker.stub(name="route_url")

        user = UserFactory.create()
        ProjectFactory.create(name="some-project")

        form = circleci.PendingCircleCIPublisherForm(
            route_url=route_url,
            check_project_name=project_service.check_project_name,
            user=user,
        )

        field = mocker.Mock(data="some-project")
        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_project_name(field)

        # The project settings URL is not shown if the user isn't an owner
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

        form = circleci.PendingCircleCIPublisherForm(
            route_url=mocker.stub(name="route_url"),
            check_project_name=check_project_name,
            user=UserFactory.build(),
        )

        field = mocker.Mock(data="some-project")
        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_project_name(field)


class TestCircleCIPublisherForm:
    def test_validate(self, mocker):
        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
            }
        )
        form = circleci.CircleCIPublisherForm(MultiDict(data))
        mocker.patch.object(form, "_lookup_project_metadata", return_value=None)

        assert form.validate()

    def test_validate_with_optional_context_id(self, mocker):
        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
                "context_id": "00000000-0000-1000-8000-000000000004",
            }
        )
        form = circleci.CircleCIPublisherForm(MultiDict(data))
        mocker.patch.object(form, "_lookup_project_metadata", return_value=None)

        assert form.validate()

    def test_validate_missing_organization_id(self, mocker):
        data = MultiDict(
            {
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
            }
        )
        form = circleci.CircleCIPublisherForm(MultiDict(data))
        mocker.patch.object(form, "_lookup_project_metadata", return_value=None)

        assert not form.validate()
        assert "circleci_org_id" in form.errors

    def test_validate_missing_project_id(self):
        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
            }
        )
        form = circleci.CircleCIPublisherForm(MultiDict(data))

        assert not form.validate()
        assert "circleci_project_id" in form.errors

    def test_validate_missing_pipeline_definition_id(self, mocker):
        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
            }
        )
        form = circleci.CircleCIPublisherForm(MultiDict(data))
        mocker.patch.object(form, "_lookup_project_metadata", return_value=None)

        assert not form.validate()
        assert "pipeline_definition_id" in form.errors

    @pytest.mark.parametrize(
        "field_name",
        [
            "circleci_org_id",
            "circleci_project_id",
            "pipeline_definition_id",
        ],
    )
    def test_validate_invalid_uuid(self, field_name, mocker):
        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
            }
        )
        data[field_name] = "not-a-valid-uuid"
        form = circleci.CircleCIPublisherForm(MultiDict(data))
        mocker.patch.object(form, "_lookup_project_metadata", return_value=None)

        assert not form.validate()
        assert field_name in form.errors

    def test_validate_invalid_context_id_uuid(self, mocker):
        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
                "context_id": "not-a-valid-uuid",
            }
        )
        form = circleci.CircleCIPublisherForm(MultiDict(data))
        mocker.patch.object(form, "_lookup_project_metadata", return_value=None)

        assert not form.validate()
        assert "context_id" in form.errors

    def test_validate_with_optional_vcs_ref(self, mocker):
        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
                "vcs_ref": "refs/heads/main",
            }
        )
        form = circleci.CircleCIPublisherForm(MultiDict(data))
        mocker.patch.object(form, "_lookup_project_metadata", return_value=None)

        assert form.validate()

    def test_validate_with_optional_vcs_origin(self, mocker):
        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
                "vcs_origin": "github.com/some-org/some-repo",
            }
        )
        form = circleci.CircleCIPublisherForm(MultiDict(data))
        mocker.patch.object(form, "_lookup_project_metadata", return_value=None)

        assert form.validate()

    def test_validate_with_all_optional_fields(self, mocker):
        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
                "context_id": "00000000-0000-1000-8000-000000000004",
                "vcs_ref": "refs/heads/main",
                "vcs_origin": "github.com/some-org/some-repo",
            }
        )
        form = circleci.CircleCIPublisherForm(MultiDict(data))
        mocker.patch.object(form, "_lookup_project_metadata", return_value=None)

        assert form.validate()

    @pytest.mark.parametrize(
        "data",
        [
            {
                "circleci_org_id": None,
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
            },
            {
                "circleci_org_id": "",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
            },
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": None,
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
            },
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
            },
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": None,
            },
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": "",
            },
        ],
    )
    def test_validate_basic_invalid_fields(self, data, mocker):
        form = circleci.CircleCIPublisherForm(MultiDict(data))
        mocker.patch.object(form, "_lookup_project_metadata", return_value=None)

        assert not form.validate()

    @pytest.mark.parametrize(
        "vcs_ref",
        [
            "refs/heads/main",
            "",
        ],
    )
    def test_vcs_ref_optional_values(self, vcs_ref, mocker):
        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
                "vcs_ref": vcs_ref,
            }
        )
        form = circleci.CircleCIPublisherForm(MultiDict(data))
        mocker.patch.object(form, "_lookup_project_metadata", return_value=None)

        assert form.validate(), str(form.errors)

    def test_vcs_ref_none_consistency(self, mocker):
        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
            }
        )
        form = circleci.CircleCIPublisherForm(MultiDict(data))
        mocker.patch.object(form, "_lookup_project_metadata", return_value=None)

        assert form.validate(), str(form.errors)
        assert form.vcs_ref.data is None

    @pytest.mark.parametrize(
        "vcs_origin",
        [
            "github.com/org/repo",
            "",
        ],
    )
    def test_vcs_origin_optional_values(self, vcs_origin, mocker):
        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
                "vcs_origin": vcs_origin,
            }
        )
        form = circleci.CircleCIPublisherForm(MultiDict(data))
        mocker.patch.object(form, "_lookup_project_metadata", return_value=None)

        assert form.validate(), str(form.errors)

    def test_vcs_origin_none_consistency(self, mocker):
        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
            }
        )
        form = circleci.CircleCIPublisherForm(MultiDict(data))
        mocker.patch.object(form, "_lookup_project_metadata", return_value=None)

        assert form.validate(), str(form.errors)
        assert form.vcs_origin.data is None

    @pytest.mark.parametrize(
        "context_id",
        [
            "00000000-0000-1000-8000-000000000004",
            "",
        ],
    )
    def test_context_id_optional_values(self, context_id, mocker):
        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
                "context_id": context_id,
            }
        )
        form = circleci.CircleCIPublisherForm(MultiDict(data))
        mocker.patch.object(form, "_lookup_project_metadata", return_value=None)

        assert form.validate(), str(form.errors)

    def test_context_id_none_consistency(self, mocker):
        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "pipeline_definition_id": "00000000-0000-1000-8000-000000000003",
            }
        )
        form = circleci.CircleCIPublisherForm(MultiDict(data))
        mocker.patch.object(form, "_lookup_project_metadata", return_value=None)

        assert form.validate(), str(form.errors)
        assert form.context_id.data is None


class TestCircleCIProjectMetadataLookup:
    @pytest.fixture
    def capture_message(self, mocker):
        return mocker.patch.object(circleci.sentry_sdk, "capture_message")

    def test_lookup_success(self, mocker):
        response = mocker.Mock(status_code=200)
        response.json.return_value = {
            "name": "my-project",
            "organization_name": "my-org",
        }
        get = mocker.patch.object(circleci.requests, "get", return_value=response)

        form = circleci.CircleCIPublisherForm()
        form._lookup_project_metadata(PROJECT_UUID)

        assert form.circleci_org_name == "my-org"
        assert form.circleci_project_name == "my-project"
        get.assert_called_once_with(
            f"https://circleci.com/api/v2/project/{PROJECT_UUID}",
            allow_redirects=True,
            timeout=5,
        )

    def test_lookup_404_private_project(self, mocker):
        response = mocker.Mock(status_code=404)
        mocker.patch.object(circleci.requests, "get", return_value=response)

        form = circleci.CircleCIPublisherForm()
        form._lookup_project_metadata(PROJECT_UUID)

        assert form.circleci_org_name is None
        assert form.circleci_project_name is None
        response.raise_for_status.assert_not_called()

    def test_lookup_http_error(self, mocker, capture_message):
        response = mocker.Mock(status_code=500)
        response.raise_for_status.side_effect = HTTPError
        mocker.patch.object(circleci.requests, "get", return_value=response)

        form = circleci.CircleCIPublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_project_metadata(PROJECT_UUID)

        capture_message.assert_called_once()

    @pytest.mark.parametrize("error", [RequestsConnectionError, Timeout])
    def test_lookup_connection_error(self, mocker, capture_message, error):
        mocker.patch.object(circleci.requests, "get", side_effect=error)

        form = circleci.CircleCIPublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_project_metadata(PROJECT_UUID)

        capture_message.assert_called_once()

    def test_lookup_invalid_json(self, mocker, capture_message):
        response = mocker.Mock(status_code=200, content=b"not-json")
        response.json.side_effect = JSONDecodeError("bad json", "not-json", 0)
        mocker.patch.object(circleci.requests, "get", return_value=response)

        form = circleci.CircleCIPublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_project_metadata(PROJECT_UUID)

        capture_message.assert_called_once()
