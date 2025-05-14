# SPDX-License-Identifier: Apache-2.0

"""
HelpDesk service implementations to interact with other services.
"""
from __future__ import annotations

import logging
import pprint
import typing

from textwrap import dedent

from pyramid_retry import RetryableException
from requests.exceptions import RequestException
from zope.interface import implementer

from .interfaces import IAdminNotificationService, IHelpDeskService

if typing.TYPE_CHECKING:
    from pyramid.request import Request
    from requests import Session


@implementer(IHelpDeskService)
class ConsoleHelpDeskService:
    """
    A HelpDeskService that prints to console instead of remote services.
    """

    def __init__(self, *, mailbox_id: str = "12345"):
        self.mailbox_id = mailbox_id

    @classmethod
    def create_service(cls, _context, _request) -> ConsoleHelpDeskService:
        logging.debug("Creating ConsoleHelpDeskService")
        return cls()

    def create_conversation(self, *, request_json: dict) -> str:
        print("Observation created")
        print("request_json:")
        print(dedent(pprint.pformat(request_json)))
        return "localhost"

    def add_tag(self, *, conversation_url: str, tag: str) -> None:
        print(f"Adding tag '{tag}' to conversation '{conversation_url}'")
        return


@implementer(IHelpDeskService)
class HelpScoutService:
    """
    A service for interacting with the HelpScout API v2.

    See: https://developer.helpscout.com/

    NOTE: Not using one of the existing `helpscout` libraries,
     because they all seem to be focused on the HelpScout API v1,
     which is deprecated. The v2 API is a bit more complex, but
     we can use the `requests` library directly to make the calls
     via our `request.http` session.
     If we see that there's further usage of the HelpScout API,
     we can look at creating a more general-purpose library/module.
    """

    def __init__(
        self, *, session: Session, bearer_token: str, mailbox_id: str | None
    ) -> None:
        self.http = session
        self.bearer_token = bearer_token
        self.mailbox_id = mailbox_id

    @classmethod
    def create_service(cls, _context, request: Request) -> HelpScoutService:
        """
        Create the service, given the context and request, and authenticate
        """
        logging.debug("Creating HelpScoutService")

        _app_id = request.registry.settings["helpscout.app_id"]
        _app_secret = request.registry.settings["helpscout.app_secret"]

        # Authenticate with HelpScout API v2 and return bearer token
        # https://developer.helpscout.com/mailbox-api/overview/authentication/#client-credentials-flow
        #
        # TODO: Ideally, we would cache this token for up to 48 hours and reuse it.
        #  For now, we'll just get a new token each time, since we're low enough volume.
        try:
            resp = request.http.post(
                "https://api.helpscout.net/v2/oauth2/token",
                json={
                    "grant_type": "client_credentials",
                    "client_id": _app_id,
                    "client_secret": _app_secret,
                },
            )
            resp.raise_for_status()
        except RequestException as e:
            raise RetryableException from e

        return cls(
            session=request.http,
            bearer_token=resp.json()["access_token"],
            mailbox_id=request.registry.settings.get("helpscout.mailbox_id"),
        )

    def create_conversation(self, *, request_json: dict) -> str:
        """
        Create a conversation in HelpScout
        https://developer.helpscout.com/mailbox-api/endpoints/conversations/create/
        """

        resp = self.http.post(
            "https://api.helpscout.net/v2/conversations",
            headers={"Authorization": f"Bearer {self.bearer_token}"},
            json=request_json,
            timeout=10,
        )
        resp.raise_for_status()
        # return the API-friendly location of the conversation
        return resp.headers["Location"]

    def add_tag(self, *, conversation_url: str, tag: str) -> None:
        """
        Add a tag to a conversation in HelpScout
        https://developer.helpscout.com/mailbox-api/endpoints/conversations/tags/update/
        """
        # Get existing tags and append new one
        resp = self.http.get(
            conversation_url, headers={"Authorization": f"Bearer {self.bearer_token}"}
        )
        resp.raise_for_status()

        # collect tag strings from response
        tags = [tag["tag"] for tag in resp.json()["tags"]]

        if tag in tags:
            # tag already exists, no need to add it
            return

        tags.append(tag)

        resp = self.http.put(
            f"{conversation_url}/tags",
            headers={"Authorization": f"Bearer {self.bearer_token}"},
            json={"tags": tags},
            timeout=10,
        )
        resp.raise_for_status()
        return


@implementer(IAdminNotificationService)
class ConsoleAdminNotificationService:
    """
    An AdminNotificationService that prints to console instead of remote services.
    """

    @classmethod
    def create_service(cls, _context, request) -> ConsoleAdminNotificationService:
        request.log.debug("Creating ConsoleWebhookNotificationService")
        return cls()

    def send_notification(self, *, payload: dict) -> None:
        print("Webhook notification sent")
        print("payload:")
        print(dedent(pprint.pformat(payload)))
        return


@implementer(IAdminNotificationService)
class SlackAdminNotificationService:
    """
    An AdminNotificationService that sends notifications to a Slack webhook.

    https://api.slack.com/messaging/webhooks
    """

    def __init__(self, *, session: Session, webhook_url: str) -> None:
        self.http = session
        self.webhook_url = webhook_url

    @classmethod
    def create_service(
        cls, _context, request: Request
    ) -> SlackAdminNotificationService:
        """
        Create the service, given the context and request
        """
        logging.debug("Creating SlackAdminNotificationService")
        return cls(
            session=request.http,
            webhook_url=request.registry.settings["helpdesk.notification_service_url"],
        )

    def send_notification(self, *, payload: dict) -> None:
        """
        Send a notification to a Slack webhook
        """
        resp = self.http.post(
            self.webhook_url,
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return
