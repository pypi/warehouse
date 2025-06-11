# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from zope.interface import Interface


class IHelpDeskService(Interface):
    def create_service(context, request) -> IHelpDeskService:
        """
        Create a new instance of the service.
        """

    def create_conversation(*, request_json: dict) -> str:
        """
        Create a new conversation in the helpdesk service.
        """

    def add_tag(*, conversation_url: str, tag: str) -> None:
        """
        Add a tag to a conversation.
        """


class IAdminNotificationService(Interface):
    def create_service(context, request) -> IAdminNotificationService:
        """
        Create a new instance of the service.
        """

    def send_notification(*, payload: dict) -> None:
        """
        Send a notification to the webhook service.
        """
