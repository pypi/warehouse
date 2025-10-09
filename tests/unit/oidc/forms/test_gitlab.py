# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest
import wtforms

from webob.multidict import MultiDict

from warehouse.oidc.forms import gitlab

from ....common.db.accounts import UserFactory
from ....common.db.packaging import (
    ProjectFactory,
    RoleFactory,
)


class TestPendingGitLabPublisherForm:
    def test_validate(self, project_service):
        route_url = pretend.stub()
        user = pretend.stub()

        data = MultiDict(
            {
                "namespace": "some-owner",
                "project": "some-repo",
                "workflow_filepath": "subfolder/some-workflow.yml",
                "project_name": "some-project",
            }
        )
        form = gitlab.PendingGitLabPublisherForm(
            MultiDict(data),
            route_url=route_url,
            check_project_name=project_service.check_project_name,
            user=user,
        )

        assert form._route_url == route_url
        assert form._check_project_name == project_service.check_project_name
        assert form._user == user
        # We're testing only the basic validation here.
        assert form.validate()

    def test_validate_project_name_already_in_use_owner(
        self, pyramid_config, project_service
    ):
        route_url = pretend.call_recorder(lambda *args, **kwargs: "my_url")

        user = UserFactory.create()
        project = ProjectFactory.create(name="some-project")
        RoleFactory.create(user=user, project=project)

        form = gitlab.PendingGitLabPublisherForm(
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
                _query={"provider": {"gitlab"}},
            )
        ]

    def test_validate_project_name_already_in_use_not_owner(
        self, pyramid_config, project_service
    ):
        route_url = pretend.call_recorder(lambda *args, **kwargs: "my_url")

        user = UserFactory.create()
        ProjectFactory.create(name="some-project")

        form = gitlab.PendingGitLabPublisherForm(
            route_url=route_url,
            check_project_name=project_service.check_project_name,
            user=user,
        )

        field = pretend.stub(data="some-project")
        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_project_name(field)

        assert route_url.calls == []


class TestGitLabPublisherForm:
    @pytest.mark.parametrize(
        "data",
        [
            {
                "namespace": "some-owner",
                "project": "some-repo",
                "workflow_filepath": "subfolder/some-workflow.yml",
            },
            {
                "namespace": "some-group/some-subgroup",
                "project": "some-repo",
                "workflow_filepath": "subfolder/some-workflow.yml",
            },
            # Leading/trailing whitespace is stripped from filepath
            {
                "namespace": "some-group/some-subgroup",
                "project": "some-repo",
                "workflow_filepath": "  subfolder/some-workflow.yml  ",
            },
        ],
    )
    def test_validate(self, data):
        form = gitlab.GitLabPublisherForm(MultiDict(data))

        # We're testing only the basic validation here.
        assert form.validate(), str(form.errors)

    @pytest.mark.parametrize(
        "data",
        [
            {"namespace": None, "project": "some", "workflow_filepath": "some"},
            {"namespace": "", "project": "some", "workflow_filepath": "some"},
            {
                "namespace": "invalid_characters@",
                "project": "some",
                "workflow_filepath": "some",
            },
            {
                "namespace": "invalid_parethen(sis",
                "project": "some",
                "workflow_filepath": "some",
            },
            {
                "namespace": "/start_with_slash",
                "project": "some",
                "workflow_filepath": "some",
            },
            {
                "namespace": "some",
                "project": "invalid space",
                "workflow_filepath": "some",
            },
            {
                "namespace": "some",
                "project": "invalid+plus",
                "workflow_filepath": "some",
            },
            {"project": None, "namespace": "some", "workflow_filepath": "some"},
            {"project": "", "namespace": "some", "workflow_filepath": "some"},
            {
                "project": "$invalid#characters",
                "namespace": "some",
                "workflow_filepath": "some",
            },
            {"project": "some", "namespace": "some", "workflow_filepath": None},
            {"project": "some", "namespace": "some", "workflow_filepath": ""},
        ],
    )
    def test_validate_basic_invalid_fields(self, data):
        form = gitlab.GitLabPublisherForm(MultiDict(data))

        # We're testing only the basic validation here.
        assert not form.validate()

    @pytest.mark.parametrize(
        "project_name",
        ["invalid.git", "invalid.atom", "invalid--project"],
    )
    def test_reserved_project_names(self, project_name):
        data = MultiDict(
            {
                "namespace": "some",
                "workflow_filepath": "subfolder/some-workflow.yml",
                "project": project_name,
            }
        )

        form = gitlab.GitLabPublisherForm(data)
        assert not form.validate()

    @pytest.mark.parametrize(
        "namespace",
        [
            "invalid.git",
            "invalid.atom",
            "consecutive--special-characters",
            "must-end-with-non-special-characters-",
        ],
    )
    def test_reserved_organization_names(self, namespace):
        data = MultiDict(
            {
                "namespace": namespace,
                "workflow_filepath": "subfolder/some-workflow.yml",
                "project": "valid-project",
            }
        )

        form = gitlab.GitLabPublisherForm(data)
        assert not form.validate()

    @pytest.mark.parametrize(
        "workflow_filepath",
        [
            "missing_suffix",
            "/begin_slash.yml",
            "end_with_slash.yml/",
            "/begin/and/end/slash.yml/",
        ],
    )
    def test_validate_workflow_filepath(self, workflow_filepath):
        form = gitlab.GitLabPublisherForm()
        field = pretend.stub(data=workflow_filepath)

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_workflow_filepath(field)

    @pytest.mark.parametrize(
        ("data", "expected"),
        [
            ("", ""),
            ("  ", ""),
            ("\t\r\n", ""),
            (None, ""),
        ],
    )
    def test_normalized_environment(self, data, expected):
        form = gitlab.GitLabPublisherForm(environment=data)
        assert form.normalized_environment == expected
