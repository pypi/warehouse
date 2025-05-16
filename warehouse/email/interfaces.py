# SPDX-License-Identifier: Apache-2.0

from zope.interface import Interface


class IEmailSender(Interface):
    def create_service(context, request):
        """
        Create the service, given the context and request for which it is being
        created for.
        """

    def send(recipient, message):
        """
        Sends an EmailMessage to the given recipient.
        """

    def last_sent(to, subject):
        """
        Determines when an email was last sent, if at all
        """
