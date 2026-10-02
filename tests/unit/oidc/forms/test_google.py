# SPDX-License-Identifier: Apache-2.0

import pytest
import wtforms

from webob.multidict import MultiDict

from warehouse.oidc.forms import google

from ....common.db.accounts import UserFactory
from ....common.db.packaging import (
    ProjectFactory,
    RoleFactory,
)


class TestPendingGooglePublisherForm:
    def test_validate(self, mocker, project_service):
        route_url = mocker.sentinel.route_url
        user = mocker.sentinel.user

        data = MultiDict(
            {
                "sub": "some-subject",
                "email": "some-email@example.com",
                "project_name": "some-project",
            }
        )
        form = google.PendingGooglePublisherForm(
            MultiDict(data),
            route_url=route_url,
            check_project_name=project_service.check_project_name,
            user=user,
        )

        assert form._check_project_name == project_service.check_project_name
        assert form._route_url == route_url
        assert form._user == user
        assert form.validate()

    def test_validate_project_name_already_in_use_owner(
        self, mocker, pyramid_config, project_service
    ):
        route_url = mocker.stub(name="route_url")
        route_url.return_value = "my_url"

        user = UserFactory.create()
        project = ProjectFactory.create(name="some-project")
        RoleFactory.create(user=user, project=project)

        form = google.PendingGooglePublisherForm(
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
            _query={"project_name": "some-project", "provider": {"google"}},
        )

    def test_validate_project_name_already_in_use_not_owner(
        self, mocker, pyramid_config, project_service
    ):
        route_url = mocker.stub(name="route_url")
        route_url.return_value = "my_url"

        user = UserFactory.create()
        ProjectFactory.create(name="some-project")

        form = google.PendingGooglePublisherForm(
            route_url=route_url,
            check_project_name=project_service.check_project_name,
            user=user,
        )

        form.project_name.data = "some-project"
        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_project_name(form.project_name)

        route_url.assert_not_called()


class TestGooglePublisherForm:
    @pytest.mark.parametrize(
        ("sub", "email"),
        [
            (None, "some-email@example.com"),
            ("some-subject", "some-email@example.com"),
        ],
    )
    def test_validate(self, sub, email):
        data = MultiDict(
            {
                "sub": sub,
                "email": email,
            }
        )
        form = google.GooglePublisherForm(MultiDict(data))

        assert form.validate(), str(form.errors)

    @pytest.mark.parametrize(
        ("sub", "email"),
        [
            ("", ""),
            (None, ""),
            ("some-subject", ""),
            ("some-subject", "invalid_email"),
        ],
    )
    def test_validate_basic_invalid_fields(self, sub, email):
        data = MultiDict(
            {
                "sub": sub,
                "email": email,
            }
        )

        form = google.GooglePublisherForm(MultiDict(data))
        assert not form.validate()
