# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest
import requests
import wtforms

from requests import ConnectionError, HTTPError, Timeout
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

_requests = requests


class TestPendingActiveStatePublisherForm:
    def test_validate(self, monkeypatch, project_service):
        route_url = pretend.stub()

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
            user=pretend.stub(),
        )

        # Test built-in validations
        monkeypatch.setattr(form, "_lookup_actor", lambda *o: {"user_id": "some-id"})

        monkeypatch.setattr(form, "_lookup_organization", lambda *o: None)

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

        form = activestate.PendingActiveStatePublisherForm(
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
                _query={"provider": {"activestate"}},
            )
        ]

    def test_validate_project_name_already_in_use_not_owner(
        self, pyramid_config, project_service
    ):
        route_url = pretend.call_recorder(lambda *args, **kwargs: "")

        user = UserFactory.create()
        ProjectFactory.create(name="some-project")

        form = activestate.PendingActiveStatePublisherForm(
            route_url=route_url,
            check_project_name=project_service.check_project_name,
            user=user,
        )

        field = pretend.stub(data="some-project")
        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_project_name(field)

        assert route_url.calls == []


class TestActiveStatePublisherForm:
    def test_validate(self, monkeypatch):
        data = MultiDict(
            {
                "organization": "some-org",
                "project": "some-project",
                "actor": "someuser",
            }
        )
        form = activestate.ActiveStatePublisherForm(MultiDict(data))

        monkeypatch.setattr(form, "_lookup_organization", lambda o: None)
        monkeypatch.setattr(form, "_lookup_actor", lambda o: fake_user_info)

        assert form.validate(), str(form.errors)

    def test_lookup_actor_404(self, monkeypatch):
        response = pretend.stub(
            status_code=404,
            raise_for_status=pretend.raiser(HTTPError),
            content=b"fake-content",
        )
        requests = pretend.stub(
            post=pretend.call_recorder(lambda o, **kw: response),
            Timeout=Timeout,
            HTTPError=HTTPError,
            ConnectionError=ConnectionError,
        )

        monkeypatch.setattr(activestate, "requests", requests)

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_actor(fake_username)

        assert requests.post.calls == [
            pretend.call(
                "https://platform.activestate.com/graphql/v1/graphql",
                json={
                    "query": "query($username: String) {users(where: {username: {_eq: $username}}) {user_id}}",  # noqa: E501
                    "variables": {"username": fake_username},
                },
                timeout=5,
            )
        ]

    def test_lookup_actor_other_http_error(self, monkeypatch):
        response = pretend.stub(
            # anything that isn't 404 or 403
            status_code=422,
            raise_for_status=pretend.raiser(HTTPError),
            content=b"fake-content",
        )
        requests = pretend.stub(
            post=pretend.call_recorder(lambda o, **kw: response),
            Timeout=Timeout,
            HTTPError=HTTPError,
            ConnectionError=ConnectionError,
        )
        monkeypatch.setattr(activestate, "requests", requests)

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(activestate, "sentry_sdk", sentry_sdk)

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_actor(fake_username)

        assert requests.post.calls == [
            pretend.call(
                "https://platform.activestate.com/graphql/v1/graphql",
                json={
                    "query": "query($username: String) {users(where: {username: {_eq: $username}}) {user_id}}",  # noqa: E501
                    "variables": {"username": fake_username},
                },
                timeout=5,
            )
        ]

        assert sentry_sdk.capture_message.calls == [
            pretend.call("Unexpected 422 error from ActiveState API: b'fake-content'")
        ]

    def test_lookup_actor_http_timeout(self, monkeypatch):
        requests = pretend.stub(
            post=pretend.raiser(Timeout),
            Timeout=Timeout,
            HTTPError=HTTPError,
            ConnectionError=ConnectionError,
        )
        monkeypatch.setattr(activestate, "requests", requests)

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(activestate, "sentry_sdk", sentry_sdk)

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_actor(fake_username)

        assert sentry_sdk.capture_message.calls == [
            pretend.call("Connection error from ActiveState API")
        ]

    def test_lookup_actor_connection_error(self, monkeypatch):
        requests = pretend.stub(
            post=pretend.raiser(ConnectionError),
            Timeout=Timeout,
            HTTPError=HTTPError,
            ConnectionError=ConnectionError,
        )
        monkeypatch.setattr(activestate, "requests", requests)

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(activestate, "sentry_sdk", sentry_sdk)

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_actor(fake_username)

        assert sentry_sdk.capture_message.calls == [
            pretend.call("Connection error from ActiveState API")
        ]

    def test_lookup_actor_non_json(self, monkeypatch):
        response = pretend.stub(
            status_code=200,
            raise_for_status=pretend.call_recorder(lambda: None),
            json=pretend.raiser(_requests.exceptions.JSONDecodeError("", "", 0)),
            content=b"",
        )

        requests = pretend.stub(
            post=pretend.call_recorder(lambda o, **kw: response),
            HTTPError=HTTPError,
            exceptions=_requests.exceptions,
        )
        monkeypatch.setattr(activestate, "requests", requests)

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(activestate, "sentry_sdk", sentry_sdk)

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_actor(fake_username)

        assert sentry_sdk.capture_message.calls == [
            pretend.call("Unexpected error from ActiveState API: b''")
        ]

    def test_lookup_actor_gql_error(self, monkeypatch):
        response = pretend.stub(
            status_code=200,
            raise_for_status=pretend.call_recorder(lambda: None),
            json=lambda: {"errors": ["some error"]},
            content=b"fake-content",
        )
        requests = pretend.stub(
            post=pretend.call_recorder(lambda o, **kw: response),
            HTTPError=HTTPError,
            exceptions=_requests.exceptions,
        )
        monkeypatch.setattr(activestate, "requests", requests)

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(activestate, "sentry_sdk", sentry_sdk)

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_actor(fake_username)

        assert requests.post.calls == [
            pretend.call(
                "https://platform.activestate.com/graphql/v1/graphql",
                json={
                    "query": "query($username: String) {users(where: {username: {_eq: $username}}) {user_id}}",  # noqa: E501
                    "variables": {"username": fake_username},
                },
                timeout=5,
            )
        ]
        assert sentry_sdk.capture_message.calls == [
            pretend.call("Unexpected error from ActiveState API: ['some error']")
        ]

    def test_lookup_actor_gql_no_data(self, monkeypatch):
        response = pretend.stub(
            status_code=200,
            raise_for_status=pretend.call_recorder(lambda: None),
            json=lambda: {"data": {"users": []}},
        )
        requests = pretend.stub(
            post=pretend.call_recorder(lambda o, **kw: response),
            HTTPError=HTTPError,
            exceptions=_requests.exceptions,
        )
        monkeypatch.setattr(activestate, "requests", requests)

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_actor(fake_username)

        assert requests.post.calls == [
            pretend.call(
                "https://platform.activestate.com/graphql/v1/graphql",
                json={
                    "query": "query($username: String) {users(where: {username: {_eq: $username}}) {user_id}}",  # noqa: E501
                    "variables": {"username": fake_username},
                },
                timeout=5,
            )
        ]

    def test_lookup_actor_succeeds(self, monkeypatch):
        response = pretend.stub(
            status_code=200,
            raise_for_status=pretend.call_recorder(lambda: None),
            json=lambda: fake_gql_user_response,
        )
        requests = pretend.stub(
            post=pretend.call_recorder(lambda o, **kw: response),
            HTTPError=HTTPError,
            requests=_requests.exceptions,
            Timeout=_requests.Timeout,
            ConnectionError=_requests.ConnectionError,
        )
        monkeypatch.setattr(activestate, "requests", requests)

        form = activestate.ActiveStatePublisherForm()
        info = form._lookup_actor(fake_username)

        assert requests.post.calls == [
            pretend.call(
                "https://platform.activestate.com/graphql/v1/graphql",
                json={
                    "query": "query($username: String) {users(where: {username: {_eq: $username}}) {user_id}}",  # noqa: E501
                    "variables": {"username": fake_username},
                },
                timeout=5,
            )
        ]
        assert info == fake_user_info

    # _lookup_organization
    def test_lookup_organization_404(self, monkeypatch):
        response = pretend.stub(
            status_code=404,
            raise_for_status=pretend.raiser(HTTPError),
            content=b"fake-content",
        )
        requests = pretend.stub(
            post=pretend.call_recorder(lambda o, **kw: response),
            HTTPError=HTTPError,
            exceptions=_requests.exceptions,
            Timeout=_requests.Timeout,
            ConnectionError=_requests.ConnectionError,
        )

        monkeypatch.setattr(activestate, "requests", requests)

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_organization(fake_org_name)

        assert requests.post.calls == [
            pretend.call(
                "https://platform.activestate.com/graphql/v1/graphql",
                json={
                    "query": "query($orgname: String) {organizations(where: {display_name: {_eq: $orgname}}) {added}}",  # noqa: E501
                    "variables": {"orgname": fake_org_name},
                },
                timeout=5,
            )
        ]

    def test_lookup_organization_other_http_error(self, monkeypatch):
        response = pretend.stub(
            # anything that isn't 404 or 403
            status_code=422,
            raise_for_status=pretend.raiser(HTTPError),
            content=b"fake-content",
        )
        requests = pretend.stub(
            post=pretend.call_recorder(lambda o, **kw: response),
            HTTPError=HTTPError,
            exceptions=_requests.exceptions,
            Timeout=_requests.Timeout,
            ConnectionError=_requests.ConnectionError,
        )
        monkeypatch.setattr(activestate, "requests", requests)

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(activestate, "sentry_sdk", sentry_sdk)

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_organization(fake_org_name)

        assert requests.post.calls == [
            pretend.call(
                "https://platform.activestate.com/graphql/v1/graphql",
                json={
                    "query": "query($orgname: String) {organizations(where: {display_name: {_eq: $orgname}}) {added}}",  # noqa: E501
                    "variables": {"orgname": fake_org_name},
                },
                timeout=5,
            )
        ]

        assert sentry_sdk.capture_message.calls == [
            pretend.call("Unexpected 422 error from ActiveState API: b'fake-content'")
        ]

    def test_lookup_organization_http_timeout(self, monkeypatch):
        requests = pretend.stub(
            post=pretend.raiser(Timeout),
            Timeout=Timeout,
            HTTPError=HTTPError,
            ConnectionError=ConnectionError,
        )
        monkeypatch.setattr(activestate, "requests", requests)

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(activestate, "sentry_sdk", sentry_sdk)

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_organization(fake_org_name)

        assert sentry_sdk.capture_message.calls == [
            pretend.call("Connection error from ActiveState API")
        ]

    def test_lookup_organization_connection_error(self, monkeypatch):
        requests = pretend.stub(
            post=pretend.raiser(ConnectionError),
            Timeout=Timeout,
            HTTPError=HTTPError,
            ConnectionError=ConnectionError,
        )
        monkeypatch.setattr(activestate, "requests", requests)

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(activestate, "sentry_sdk", sentry_sdk)

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_organization(fake_org_name)

        assert sentry_sdk.capture_message.calls == [
            pretend.call("Connection error from ActiveState API")
        ]

    def test_lookup_organization_non_json(self, monkeypatch):
        response = pretend.stub(
            status_code=200,
            raise_for_status=pretend.call_recorder(lambda: None),
            json=pretend.raiser(_requests.exceptions.JSONDecodeError("", "", 0)),
            content=b"",
        )

        requests = pretend.stub(
            post=pretend.call_recorder(lambda o, **kw: response),
            HTTPError=HTTPError,
            exceptions=_requests.exceptions,
        )
        monkeypatch.setattr(activestate, "requests", requests)

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(activestate, "sentry_sdk", sentry_sdk)

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_organization(fake_org_name)

        assert sentry_sdk.capture_message.calls == [
            pretend.call("Unexpected error from ActiveState API: b''")
        ]

    def test_lookup_organization_gql_error(self, monkeypatch):
        response = pretend.stub(
            status_code=200,
            raise_for_status=pretend.call_recorder(lambda: None),
            json=lambda: {"errors": ["some error"]},
            content=b'{"errors": ["some error"]}',
        )

        requests = pretend.stub(
            post=pretend.call_recorder(lambda o, **kw: response),
            HTTPError=HTTPError,
            exceptions=_requests.exceptions,
        )
        monkeypatch.setattr(activestate, "requests", requests)

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(activestate, "sentry_sdk", sentry_sdk)

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_organization(fake_org_name)

        assert requests.post.calls == [
            pretend.call(
                "https://platform.activestate.com/graphql/v1/graphql",
                json={
                    "query": "query($orgname: String) {organizations(where: {display_name: {_eq: $orgname}}) {added}}",  # noqa: E501
                    "variables": {"orgname": fake_org_name},
                },
                timeout=5,
            )
        ]
        assert sentry_sdk.capture_message.calls == [
            pretend.call("Unexpected error from ActiveState API: ['some error']")
        ]

    def test_lookup_organization_gql_no_data(self, monkeypatch):
        response = pretend.stub(
            status_code=200,
            raise_for_status=pretend.call_recorder(lambda: None),
            json=lambda: {"data": {"organizations": []}},
            content='{"data": {"organizations": []}}',
        )
        requests = pretend.stub(
            post=pretend.call_recorder(lambda o, **kw: response),
            HTTPError=HTTPError,
            exceptions=_requests.exceptions,
        )
        monkeypatch.setattr(activestate, "requests", requests)

        form = activestate.ActiveStatePublisherForm()
        with pytest.raises(wtforms.validators.ValidationError):
            form._lookup_organization(fake_org_name)

        assert requests.post.calls == [
            pretend.call(
                "https://platform.activestate.com/graphql/v1/graphql",
                json={
                    "query": "query($orgname: String) {organizations(where: {display_name: {_eq: $orgname}}) {added}}",  # noqa: E501
                    "variables": {"orgname": fake_org_name},
                },
                timeout=5,
            )
        ]

    def test_lookup_organization_succeeds(self, monkeypatch):
        response = pretend.stub(
            status_code=200,
            json=lambda: fake_gql_org_response,
        )
        requests = pretend.stub(
            post=pretend.call_recorder(lambda o, **kw: response), HTTPError=HTTPError
        )
        monkeypatch.setattr(activestate, "requests", requests)

        form = activestate.ActiveStatePublisherForm()
        form._lookup_organization(fake_org_name)

        assert requests.post.calls == [
            pretend.call(
                "https://platform.activestate.com/graphql/v1/graphql",
                json={
                    "query": "query($orgname: String) {organizations(where: {display_name: {_eq: $orgname}}) {added}}",  # noqa: E501
                    "variables": {"orgname": fake_org_name},
                },
                timeout=5,
            )
        ]

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
    def test_validate_basic_invalid_fields(self, monkeypatch, data):
        print(data)
        form = activestate.ActiveStatePublisherForm(MultiDict(data))

        monkeypatch.setattr(form, "_lookup_actor", lambda o: fake_user_info)
        monkeypatch.setattr(form, "_lookup_organization", lambda o: None)

        assert not form.validate()

    def test_validate_owner(self, monkeypatch):
        form = activestate.ActiveStatePublisherForm()

        monkeypatch.setattr(form, "_lookup_actor", lambda o: fake_user_info)

        field = pretend.stub(data=fake_username)
        form.validate_actor(field)

        assert form.actor_id == "some-user-id"
