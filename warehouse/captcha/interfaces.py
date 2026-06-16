# SPDX-License-Identifier: Apache-2.0

from typing import Any, NamedTuple

from zope.interface import Interface


class ChallengeResponse(NamedTuple):
    challenge_ts: Any
    hostname: Any


class ICaptchaService(Interface):
    def create_service(context, request):
        """
        Create the service, given the context and request for which it is being
        created for, passing a name for settings.
        """

    def enabled() -> bool:
        """
        Return whether the Captcha service is enabled.
        """

    def csp_policy() -> dict[str, list[str]]:
        """
        Return the CSP policy appropriate for the Captcha service.
        """

    def verify_response(response) -> ChallengeResponse | None:
        """
        Verify the response from the Captcha service.
        """
