# SPDX-License-Identifier: Apache-2.0

import json

import pytest
import responses
import wtforms

from webob.multidict import MultiDict

from warehouse.oidc.forms import activestate

from ....common.db.accounts import UserFactory
from ....common.db.packaging import (
    ProjectFactory,
    RoleFactory,
)

fake_username = "some-username"
fake_org_name = "some-org"
fake_user_info = {"user_id": "some-user-id"}
fake_org_info = {"added": "somedatestring"}
fake_gql_org_response = {"data": {"organizations": [fake_org_info]}}
fake_gql_user_response = {"data": {"users": [fake_user_info]}}

_GRAPHQL_URL = "https://platform.activestate.com/graphql/v1/graphql"


class TestPendingActiveStatePublisherForm:
    def test_validate(self, mocker, project_service):
        route_url = mocker.sentinel.route_url

        data = MultiDict(
            {
                "organization": "some-org",
                "project": "some-project",
                "actor": "someuser",
                "project_name": "some-project",
            }
        )
        form = activestate.PendingActiveStatePublisherForm(
            MultiDict(data),
            route_url=route_url,
            check_project_name=project_service.check_project_name,
            user=mocker.sentinel.user,
        )

        # Test built-in validations
        mocker.patch.object(form, "_lookup_actor", return_value={"user_id": "some-id"})
        mocker.patch.object(form, "_lookup_organization", return_value=None)

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

        form = activestate.PendingActiveStatePublisherForm(
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
            _query={"project_name": "some-project", "provider": {"activestate"}},
        )

    def test_validate_project_name_already_in_use_not_owner(
        self, mocker, pyramid_config, project_service
    ):
        route_url = mocker.stub(name="route_url")
        route_url.return_value = ""

        user = UserFactory.create()
        ProjectFactory.create(name="some-project")

        form = activestate.PendingActiveStatePublisherForm(
            route_url=route_url,
            check_project_name=project_service.check_project_name,
            user=user,
        )

        form.project_name.data = "some-project"
        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_project_name(form.project_name)

        route_url.assert_not_called()


class TestActiveStatePublisherForm:
    def test_validate(self, mocker):
        data = MultiDict(
            {
                "organization": "some-org",
                "project": "some-project",
                "actor": "someuser",
            }
        )
        form = activestate.ActiveStatePublisherForm(MultiDict(data))

        mocker.patch.object(form, "_lookup_organization", return_value=None)
        mocker.patch.object(form, "_lookup_actor", return_value=fake_user_info)

        assert form.validate(), str(form.errors)

    @responses.activate
    def test_lookup_actor_404(self):
        responses.add(responses.POST, _GRAPHQL_URL, status=404, body=b"fake-content")

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_actor(fake_username)

        assert len(responses.calls) == 1
        assert responses.calls[0].request.req_kwargs["timeout"] == 5
        sent = json.loads(responses.calls[0].request.body)
        assert sent == {
            "query": (
                "query($username: String) {users(where: {username: "
                "{_eq: $username}}) {user_id}}"
            ),
            "variables": {"username": fake_username},
        }

    @responses.activate
    def test_lookup_actor_other_http_error(self, mocker):
        capture_message = mocker.patch.object(
            activestate.sentry_sdk, "capture_message", autospec=True
        )
        # anything that isn't 404
        responses.add(responses.POST, _GRAPHQL_URL, status=422, body=b"fake-content")

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_actor(fake_username)

        assert len(responses.calls) == 1
        capture_message.assert_called_once_with(
            "Unexpected 422 error from ActiveState API: b'fake-content'"
        )

    @responses.activate
    def test_lookup_actor_http_timeout(self, mocker):
        capture_message = mocker.patch.object(
            activestate.sentry_sdk, "capture_message", autospec=True
        )
        responses.add(responses.POST, _GRAPHQL_URL, body=activestate.requests.Timeout())

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_actor(fake_username)

        capture_message.assert_called_once_with("Connection error from ActiveState API")

    @responses.activate
    def test_lookup_actor_connection_error(self, mocker):
        capture_message = mocker.patch.object(
            activestate.sentry_sdk, "capture_message", autospec=True
        )
        responses.add(
            responses.POST, _GRAPHQL_URL, body=activestate.requests.ConnectionError()
        )

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_actor(fake_username)

        capture_message.assert_called_once_with("Connection error from ActiveState API")

    @responses.activate
    def test_lookup_actor_non_json(self, mocker):
        capture_message = mocker.patch.object(
            activestate.sentry_sdk, "capture_message", autospec=True
        )
        responses.add(responses.POST, _GRAPHQL_URL, status=200, body=b"")

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_actor(fake_username)

        capture_message.assert_called_once_with(
            "Unexpected error from ActiveState API: b''"
        )

    @responses.activate
    def test_lookup_actor_gql_error(self, mocker):
        capture_message = mocker.patch.object(
            activestate.sentry_sdk, "capture_message", autospec=True
        )
        responses.add(responses.POST, _GRAPHQL_URL, json={"errors": ["some error"]})

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_actor(fake_username)

        assert len(responses.calls) == 1
        sent = json.loads(responses.calls[0].request.body)
        assert sent["variables"] == {"username": fake_username}
        capture_message.assert_called_once_with(
            "Unexpected error from ActiveState API: ['some error']"
        )

    @responses.activate
    def test_lookup_actor_gql_no_data(self):
        responses.add(responses.POST, _GRAPHQL_URL, json={"data": {"users": []}})

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_actor(fake_username)

        assert len(responses.calls) == 1
        sent = json.loads(responses.calls[0].request.body)
        assert sent["variables"] == {"username": fake_username}

    @responses.activate
    def test_lookup_actor_succeeds(self):
        responses.add(responses.POST, _GRAPHQL_URL, json=fake_gql_user_response)

        form = activestate.ActiveStatePublisherForm()
        info = form._lookup_actor(fake_username)

        assert len(responses.calls) == 1
        sent = json.loads(responses.calls[0].request.body)
        assert sent == {
            "query": (
                "query($username: String) {users(where: {username: "
                "{_eq: $username}}) {user_id}}"
            ),
            "variables": {"username": fake_username},
        }
        assert info == fake_user_info

    # _lookup_organization
    @responses.activate
    def test_lookup_organization_404(self):
        responses.add(responses.POST, _GRAPHQL_URL, status=404, body=b"fake-content")

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_organization(fake_org_name)

        assert len(responses.calls) == 1
        sent = json.loads(responses.calls[0].request.body)
        assert sent["variables"] == {"orgname": fake_org_name}

    @responses.activate
    def test_lookup_organization_other_http_error(self, mocker):
        capture_message = mocker.patch.object(
            activestate.sentry_sdk, "capture_message", autospec=True
        )
        # anything that isn't 404
        responses.add(responses.POST, _GRAPHQL_URL, status=422, body=b"fake-content")

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_organization(fake_org_name)

        assert len(responses.calls) == 1
        capture_message.assert_called_once_with(
            "Unexpected 422 error from ActiveState API: b'fake-content'"
        )

    @responses.activate
    def test_lookup_organization_http_timeout(self, mocker):
        capture_message = mocker.patch.object(
            activestate.sentry_sdk, "capture_message", autospec=True
        )
        responses.add(responses.POST, _GRAPHQL_URL, body=activestate.requests.Timeout())

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_organization(fake_org_name)

        capture_message.assert_called_once_with("Connection error from ActiveState API")

    @responses.activate
    def test_lookup_organization_connection_error(self, mocker):
        capture_message = mocker.patch.object(
            activestate.sentry_sdk, "capture_message", autospec=True
        )
        responses.add(
            responses.POST, _GRAPHQL_URL, body=activestate.requests.ConnectionError()
        )

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_organization(fake_org_name)

        capture_message.assert_called_once_with("Connection error from ActiveState API")

    @responses.activate
    def test_lookup_organization_non_json(self, mocker):
        capture_message = mocker.patch.object(
            activestate.sentry_sdk, "capture_message", autospec=True
        )
        responses.add(responses.POST, _GRAPHQL_URL, status=200, body=b"")

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_organization(fake_org_name)

        capture_message.assert_called_once_with(
            "Unexpected error from ActiveState API: b''"
        )

    @responses.activate
    def test_lookup_organization_gql_error(self, mocker):
        capture_message = mocker.patch.object(
            activestate.sentry_sdk, "capture_message", autospec=True
        )
        responses.add(responses.POST, _GRAPHQL_URL, json={"errors": ["some error"]})

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_organization(fake_org_name)

        assert len(responses.calls) == 1
        sent = json.loads(responses.calls[0].request.body)
        assert sent["variables"] == {"orgname": fake_org_name}
        capture_message.assert_called_once_with(
            "Unexpected error from ActiveState API: ['some error']"
        )

    @responses.activate
    def test_lookup_organization_gql_no_data(self):
        responses.add(
            responses.POST, _GRAPHQL_URL, json={"data": {"organizations": []}}
        )

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_organization(fake_org_name)

        assert len(responses.calls) == 1
        sent = json.loads(responses.calls[0].request.body)
        assert sent["variables"] == {"orgname": fake_org_name}

    @responses.activate
    def test_lookup_organization_succeeds(self):
        responses.add(responses.POST, _GRAPHQL_URL, json=fake_gql_org_response)

        form = activestate.ActiveStatePublisherForm()
        form._lookup_organization(fake_org_name)

        assert len(responses.calls) == 1
        sent = json.loads(responses.calls[0].request.body)
        assert sent == {
            "query": (
                "query($orgname: String) {organizations(where: {display_name: "
                "{_eq: $orgname}}) {added}}"
            ),
            "variables": {"orgname": fake_org_name},
        }

    @pytest.mark.parametrize(
        "data",
        [
            # Organization
            # Missing
            # Empty
            {"organization": "", "project": "good", "actor": "good"},
            # Actor
            # Missing
            # Empty
            {"actor": "", "project": "good", "organization": "good"},
            {"actor": None, "project": "good", "organization": "good"},
            # Project
            # Too short
            # Too long
            # Invalid characters
            # No leading or ending -
            # No double --
            # Missing
            # Empty
            {"project": "AB", "actor": "good", "organization": "good"},
            {
                "project": "abcdefghojklmnopqrstuvwxyz123456789012345",
                "actor": "good",
                "organization": "good",
            },
            {
                "project": "invalid_characters@",
                "actor": "good",
                "organization": "good",
            },
            {"project": "-foo-", "actor": "good", "organization": "good"},
            {"project": "---", "actor": "good", "organization": "good"},
            {"project": "", "actor": "good", "organization": "good"},
            {"project": None, "actor": "good", "organization": "good"},
        ],
    )
    def test_validate_basic_invalid_fields(self, mocker, data):
        form = activestate.ActiveStatePublisherForm(MultiDict(data))

        mocker.patch.object(form, "_lookup_actor", return_value=fake_user_info)
        mocker.patch.object(form, "_lookup_organization", return_value=None)

        assert not form.validate()

    def test_validate_owner(self, mocker):
        form = activestate.ActiveStatePublisherForm()

        mocker.patch.object(form, "_lookup_actor", return_value=fake_user_info)

        form.actor.data = fake_username
        form.validate_actor(form.actor)

        assert form.actor_id == "some-user-id"
