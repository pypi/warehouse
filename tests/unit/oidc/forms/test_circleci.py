# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest
import wtforms

from webob.multidict import MultiDict

from warehouse.oidc.forms import circleci

from ....common.db.accounts import UserFactory
from ....common.db.packaging import (
    ProjectFactory,
    RoleFactory,
)


class TestPendingCircleCIPublisherForm:
    def test_validate(self, monkeypatch, project_service):
        route_url = pretend.stub()

        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
                "project_name": "some-project",
            }
        )
        form = circleci.PendingCircleCIPublisherForm(
            MultiDict(data),
            route_url=route_url,
            check_project_name=project_service.check_project_name,
            user=pretend.stub(),
        )

        assert form._check_project_name == project_service.check_project_name
        assert form._route_url == route_url
        assert form.validate()

    def test_validate_project_name_already_in_use_owner(
        self, pyramid_config, project_service
    ):
        route_url = pretend.call_recorder(lambda *args, **kwargs: "")

        user = UserFactory.create()
        project = ProjectFactory.create(name="some-project")
        RoleFactory.create(user=user, project=project)

        form = circleci.PendingCircleCIPublisherForm(
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
                _query={"provider": {"circleci"}},
            )
        ]

    def test_validate_project_name_already_in_use_not_owner(
        self, pyramid_config, project_service
    ):
        route_url = pretend.call_recorder(lambda *args, **kwargs: "")

        user = UserFactory.create()
        ProjectFactory.create(name="some-project")

        form = circleci.PendingCircleCIPublisherForm(
            route_url=route_url,
            check_project_name=project_service.check_project_name,
            user=user,
        )

        field = pretend.stub(data="some-project")
        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_project_name(field)

        # The project settings URL is not shown if the user isn't an owner
        assert route_url.calls == []


class TestCircleCIPublisherForm:
    def test_validate(self):
        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
            }
        )
        form = circleci.CircleCIPublisherForm(MultiDict(data))

        assert form.validate()

    def test_validate_missing_organization_id(self):
        data = MultiDict(
            {
                "circleci_project_id": "00000000-0000-1000-8000-000000000002",
            }
        )
        form = circleci.CircleCIPublisherForm(MultiDict(data))

        assert not form.validate()
        assert "circleci_org_id" in form.errors

    def test_validate_missing_project_id(self):
        data = MultiDict(
            {
                "circleci_org_id": "00000000-0000-1000-8000-000000000001",
            }
        )
        form = circleci.CircleCIPublisherForm(MultiDict(data))

        assert not form.validate()
        assert "circleci_project_id" in form.errors
