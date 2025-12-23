# SPDX-License-Identifier: Apache-2.0

"""
OAuth integration for account associations.

Provides OAuth client functionality for external service integration.
"""

from __future__ import annotations

import secrets
import urllib.parse

from typing import TYPE_CHECKING, Self

import requests

from zope.interface import Interface, implementer

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pyramid.request import Request


class IOAuthProviderService(Interface):  # noqa: N805
    """
    Interface for OAuth provider clients.

    OAuth providers must implement authorization URL generation,
    token exchange, and user info fetching.
    """

    def create_service(context, request):  # noqa: N805
        """
        Create appropriate OAuth client based on configuration.
        """

    def generate_authorize_url(state, scopes=None):  # noqa: N805
        """
        Generate OAuth authorization URL with CSRF state token.

        Returns URL to redirect user to for authorization.
        """

    def exchange_code_for_token(code):  # noqa: N805
        """
        Exchange authorization code for access token.

        Returns dict with 'access_token', 'token_type', 'scope', etc.
        """

    def get_user_info(access_token):  # noqa: N805
        """
        Fetch user information from OAuth provider.

        Returns dict with user info including 'id', 'login'/'username', etc.
        """


@implementer(IOAuthProviderService)
class GitHubOAuthClient:
    """
    OAuth client for GitHub integration.

    Configuration required in settings:
    - github.oauth.client_id
    - github.oauth.client_secret
    - github.oauth.redirect_uri (or use request.route_url)
    """

    AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    USER_API_URL = "https://api.github.com/user"

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    @classmethod
    def create_service(cls, context, request: Request) -> Self:
        """
        Create GitHubOAuthClient from request settings.
        """
        settings = request.registry.settings
        redirect_uri = request.route_url("manage.account.associations.github.callback")

        return cls(
            client_id=settings["github.oauth.client_id"],
            client_secret=settings["github.oauth.client_secret"],
            redirect_uri=redirect_uri,
        )

    def generate_authorize_url(
        self, state: str, scopes: Sequence[str] | None = None
    ) -> str:
        """
        Generate the GitHub OAuth authorization URL.

        Args:
            state: CSRF protection token (store in session)
            scopes: Sequence of OAuth scopes to request

        Returns:
            Authorization URL to redirect user to
        """
        if scopes is None:
            scopes = ["read:user", "user:email"]

        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
        }
        return f"{self.AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> dict[str, str]:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from GitHub callback

        Returns:
            Dict with 'access_token', 'token_type', 'scope'

        Raises:
            requests.HTTPError: If token exchange fails
        """
        response = requests.post(
            self.TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": self.redirect_uri,
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
        data: dict[str, str] = response.json()
        return data

    def get_user_info(self, access_token: str) -> dict[str, str | int]:
        """
        Fetch user information from GitHub API.

        Args:
            access_token: OAuth access token

        Returns:
            Dict with user info including 'id', 'login', 'email', etc.

        Raises:
            requests.HTTPError: If API request fails
        """
        response = requests.get(
            self.USER_API_URL,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
            timeout=10,
        )
        response.raise_for_status()
        data: dict[str, str | int] = response.json()
        return data


@implementer(IOAuthProviderService)
class NullOAuthClient:
    """
    Null OAuth client for testing and development.

    Returns mock data without making real OAuth requests.
    Useful for local development without configuring OAuth apps.
    """

    def __init__(
        self,
        client_id: str = "null",
        client_secret: str = "null",
        redirect_uri: str = "http://localhost",
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    @classmethod
    def create_service(cls, context, request: Request) -> Self:
        """
        Create NullOAuthClient for testing/development.
        """
        redirect_uri = request.route_url("manage.account.associations.github.callback")
        return cls(redirect_uri=redirect_uri)

    def generate_authorize_url(
        self, state: str, scopes: Sequence[str] | None = None
    ) -> str:
        """
        Generate mock authorization URL.

        In development, this redirects back to callback with mock code.
        """
        # Return a mock URL that includes the state and a test code
        params = {
            "code": "mock_authorization_code",
            "state": state,
        }
        return f"{self.redirect_uri}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> dict[str, str]:
        """
        Return mock access token.
        """
        return {
            "access_token": "mock_access_token_" + secrets.token_hex(16),
            "token_type": "bearer",
            "scope": "read:user user:email",
        }

    def get_user_info(self, access_token: str) -> dict[str, str | int]:
        """
        Return mock user info.
        """
        # Generate consistent mock data based on token
        mock_id = abs(hash(access_token)) % 1000000
        return {
            "id": mock_id,
            "login": f"mockuser_{mock_id}",
            "name": f"Mock User {mock_id}",
            "email": f"mock_{mock_id}@example.com",
        }


def generate_state_token() -> str:
    """Generate a secure random state token for CSRF protection."""
    return secrets.token_urlsafe(32)
