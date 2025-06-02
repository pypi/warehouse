# SPDX-License-Identifier: Apache-2.0

import http

from textwrap import dedent

import pretend
import pytest
import requests
import responses

from pyramid_retry import RetryableException
from zope.interface.verify import verifyClass

from warehouse.helpdesk.interfaces import IAdminNotificationService, IHelpDeskService
from warehouse.helpdesk.services import (
    ConsoleAdminNotificationService,
    ConsoleHelpDeskService,
    HelpScoutService,
    SlackAdminNotificationService,
)


@pytest.mark.parametrize("service_class", [ConsoleHelpDeskService, HelpScoutService])
class TestHelpDeskService:
    """Common tests for the service interface."""

    def test_verify_service_class(self, service_class):
        assert verifyClass(IHelpDeskService, service_class)

    @responses.activate
    def test_create_service(self, service_class):
        responses.add(
            responses.POST,
            "https://api.helpscout.net/v2/oauth2/token",
            json={"access_token": "NOT_REAL_TOKEN"},
        )

        context = None
        request = pretend.stub(
            http=requests.Session(),
            registry=pretend.stub(
                settings={
                    "helpscout.app_id": "an insecure helpscout app id",
                    "helpscout.app_secret": "an insecure helpscout app secret",
                },
            ),
        )

        service = service_class.create_service(context, request)
        assert isinstance(service, service_class)


class TestConsoleHelpDeskService:
    def test_create_service(self):
        service = ConsoleHelpDeskService.create_service(None, None)
        assert isinstance(service, ConsoleHelpDeskService)

    def test_create_conversation(self, capsys):
        service = ConsoleHelpDeskService()

        service.create_conversation(
            request_json={
                "email": "foo@example.com",
                "name": "Foo Bar",
                "subject": "Test",
                "message": "Hello, World!",
            }
        )

        captured = capsys.readouterr()

        expected = dedent(
            """\
            Observation created
            request_json:
            {'email': 'foo@example.com',
             'message': 'Hello, World!',
             'name': 'Foo Bar',
             'subject': 'Test'}
            """
        )
        assert captured.out == expected


class TestHelpScoutService:
    @pytest.mark.parametrize(
        "partial_setting", ["helpscout.app_id", "helpscout.app_secret"]
    )
    def test_create_service_fails_when_missing_setting(self, partial_setting):
        context = None
        request = pretend.stub(
            http=pretend.stub(),
            registry=pretend.stub(settings={partial_setting: "some value"}),
        )

        with pytest.raises(KeyError):
            HelpScoutService.create_service(context, request)

    @responses.activate
    def test_retries_on_error(self):
        responses.add(
            responses.POST,
            "https://api.helpscout.net/v2/oauth2/token",
            body=requests.exceptions.RequestException(),
        )

        context = None
        request = pretend.stub(
            http=requests.Session(),
            registry=pretend.stub(
                settings={
                    "helpscout.app_id": "an insecure helpscout app id",
                    "helpscout.app_secret": "an insecure helpscout app secret",
                },
            ),
        )

        with pytest.raises(RetryableException):
            HelpScoutService.create_service(context, request)

    @responses.activate
    def test_create_conversation(self):
        responses.add(
            responses.POST,
            "https://api.helpscout.net/v2/conversations",
            headers={"Location": "https://api.helpscout.net/v2/conversations/123"},
            json=None,
        )

        service = HelpScoutService(
            session=requests.Session(),
            bearer_token="fake token",
            mailbox_id="12345",
        )

        resp = service.create_conversation(
            request_json={
                "email": "foo@example.com",
                "name": "Foo Bar",
                "subject": "Test",
                "message": "Hello, World!",
            }
        )

        assert resp == "https://api.helpscout.net/v2/conversations/123"
        assert len(responses.calls) == 1

    @responses.activate
    def test_add_tag(self):
        responses.get(
            "https://api.helpscout.net/v2/conversations/123",
            headers={"Content-Type": "application/hal+json"},
            json={"tags": [{"id": 9150, "color": "#929499", "tag": "existing_tag"}]},
        )
        responses.put(
            "https://api.helpscout.net/v2/conversations/123/tags",
            match=[
                responses.matchers.json_params_matcher(
                    {"tags": ["existing_tag", "added_tag"]}
                )
            ],
            status=http.HTTPStatus.NO_CONTENT,
        )

        service = HelpScoutService(
            session=requests.Session(),
            bearer_token="fake token",
            mailbox_id="12345",
        )

        service.add_tag(
            conversation_url="https://api.helpscout.net/v2/conversations/123",
            tag="added_tag",
        )

        assert len(responses.calls) == 2
        # GET call
        get_call = responses.calls[0]
        assert get_call.request.url == "https://api.helpscout.net/v2/conversations/123"
        assert get_call.request.headers["Authorization"] == "Bearer fake token"
        assert get_call.response.json() == {
            "tags": [{"id": 9150, "color": "#929499", "tag": "existing_tag"}]
        }
        # PUT call
        put_call = responses.calls[1]
        assert (
            put_call.request.url
            == "https://api.helpscout.net/v2/conversations/123/tags"
        )
        assert put_call.request.headers["Authorization"] == "Bearer fake token"
        assert put_call.response.status_code == http.HTTPStatus.NO_CONTENT

    @responses.activate
    def test_add_tag_with_duplicate(self):
        responses.get(
            "https://api.helpscout.net/v2/conversations/123",
            headers={"Content-Type": "application/hal+json"},
            json={"tags": [{"id": 9150, "color": "#929499", "tag": "existing_tag"}]},
        )

        service = HelpScoutService(
            session=requests.Session(),
            bearer_token="fake token",
            mailbox_id="12345",
        )

        service.add_tag(
            conversation_url="https://api.helpscout.net/v2/conversations/123",
            tag="existing_tag",
        )

        # No PUT call should be made
        assert len(responses.calls) == 1


@pytest.mark.parametrize(
    "service_class", [ConsoleAdminNotificationService, SlackAdminNotificationService]
)
class TestAdminNotificationService:
    """Common tests for the service interface."""

    def test_verify_service_class(self, service_class):
        assert verifyClass(IAdminNotificationService, service_class)

    def test_create_service(self, service_class):
        context = None
        request = pretend.stub(
            http=pretend.stub(),
            log=pretend.stub(
                debug=pretend.call_recorder(lambda msg: None),
            ),
            registry=pretend.stub(
                settings={
                    "helpdesk.notification_service_url": "https://webhook.example/1234",
                }
            ),
        )

        service = service_class.create_service(context, request)
        assert isinstance(service, service_class)


class TestConsoleAdminNotificationService:
    def test_send_notification(self, capsys):
        service = ConsoleAdminNotificationService()

        service.send_notification(payload={"text": "Hello, World!"})

        captured = capsys.readouterr()

        expected = dedent(
            """\
            Webhook notification sent
            payload:
            {'text': 'Hello, World!'}
            """
        )
        assert captured.out == expected


class TestSlackAdminNotificationService:
    @responses.activate
    def test_send_notification(self):
        responses.add(
            responses.POST,
            "https://webhook.example/1234",
            json={"ok": True},
        )

        service = SlackAdminNotificationService(
            session=requests.Session(),
            webhook_url="https://webhook.example/1234",
        )

        service.send_notification(payload={"text": "Hello, World!"})

        assert len(responses.calls) == 1
        post_call = responses.calls[0]
        assert post_call.request.url == "https://webhook.example/1234"
        assert post_call.response.json() == {"ok": True}
