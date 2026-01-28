# SPDX-License-Identifier: Apache-2.0

"""
OAuth integration for account associations.

Provides OAuth client functionality for external service integration.
"""

from __future__ import annotations

import secrets
import urllib.parse
import warnings

from typing import TYPE_CHECKING, Self

import requests

from zope.interface import Interface, implementer

from warehouse.utils.exceptions import NullOAuthProviderServiceWarning

if TYPE_CHECKING:
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

    def generate_authorize_url(state):  # noqa: N805
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
class GitHubAppClient:
    """
    GitHub App client for user authentication and future repository access.

    Uses GitHub App's OAuth flow for user identity verification.
    Permissions are configured in the GitHub App settings, not requested at
    authorization time. This provides fine-grained access control.

    Configuration required in settings:
    - github.oauth.client_id: GitHub App's OAuth client ID
    - github.oauth.client_secret: GitHub App's OAuth client secret

    Future configuration (for repository access):
    - github.oauth.app_id: GitHub App ID (for installation API)
    - github.oauth.private_key: GitHub App private key (for JWT signing)

    See: https://docs.github.com/en/apps/creating-github-apps
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
        Create GitHubAppClient from request settings.
        """
        settings = request.registry.settings
        redirect_uri = request.route_url("manage.account.associations.github.callback")

        return cls(
            client_id=settings["github.oauth.client_id"],
            client_secret=settings["github.oauth.client_secret"],
            redirect_uri=redirect_uri,
        )

    def generate_authorize_url(self, state: str) -> str:
        """
        Generate the GitHub App OAuth authorization URL.

        Unlike OAuth Apps, GitHub Apps don't request scopes at authorization time.
        Permissions are configured in the GitHub App settings and apply
        automatically when the user authorizes.

        Args:
            state: CSRF protection token (store in session)

        Returns:
            Authorization URL to redirect user to
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
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
class GitLabOAuthClient:
    """
    GitLab OAuth client for user authentication.

    Uses GitLab's standard OAuth 2.0 flow with the read_user scope for
    identity verification. Unlike GitHub Apps, GitLab OAuth requires
    explicit scope requests at authorization time.

    Configuration required in settings:
    - gitlab.oauth.client_id: GitLab OAuth client ID
    - gitlab.oauth.client_secret: GitLab OAuth client secret

    Note: GitLab tokens expire after 2 hours, but since we only use them
    for immediate identity verification (not stored), this doesn't affect us.

    See: https://docs.gitlab.com/ee/api/oauth2.html
    """

    AUTHORIZE_URL = "https://gitlab.com/oauth/authorize"
    TOKEN_URL = "https://gitlab.com/oauth/token"
    USER_API_URL = "https://gitlab.com/api/v4/user"

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    @classmethod
    def create_service(cls, context, request: Request) -> Self:
        """
        Create GitLabOAuthClient from request settings.
        """
        settings = request.registry.settings
        redirect_uri = request.route_url("manage.account.associations.gitlab.callback")

        return cls(
            client_id=settings["gitlab.oauth.client_id"],
            client_secret=settings["gitlab.oauth.client_secret"],
            redirect_uri=redirect_uri,
        )

    def generate_authorize_url(self, state: str) -> str:
        """
        Generate the GitLab OAuth authorization URL.

        Args:
            state: CSRF protection token (store in session)

        Returns:
            Authorization URL to redirect user to
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "state": state,
            "scope": "read_user",
        }
        return f"{self.AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> dict[str, str]:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from GitLab callback

        Returns:
            Dict with 'access_token', 'token_type', 'expires_in', etc.

        Raises:
            requests.HTTPError: If token exchange fails
        """
        response = requests.post(
            self.TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
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
        Fetch user information from GitLab API.

        Args:
            access_token: OAuth access token

        Returns:
            Dict with user info including 'id', 'username', 'email', etc.

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


class _NullOAuthClientBase:
    """
    Base class for null OAuth clients (testing and development ONLY).

    WARNING: These services should NEVER be used in production environments.
    They create fake user associations without any actual OAuth verification,
    which would allow anyone to associate arbitrary external accounts.

    Subclasses implement IOAuthProviderService for use in development.
    """

    _provider: str  # Set by subclasses
    _callback_route: str  # Set by subclasses

    def __init__(self, redirect_uri: str):
        warnings.warn(
            f"{self.__class__.__name__} is intended only for use in development, "
            "you should not use it in production due to the creation of "
            "fake user associations without actual OAuth verification.",
            NullOAuthProviderServiceWarning,
        )
        self.redirect_uri = redirect_uri

    @classmethod
    def create_service(cls, context, request: Request) -> Self:
        redirect_uri = request.route_url(cls._callback_route)
        return cls(redirect_uri=redirect_uri)

    def generate_authorize_url(self, state: str) -> str:
        """Generate mock authorization URL that redirects back with mock code."""
        params = {
            "code": f"mock_{self._provider}_authorization_code",
            "state": state,
        }
        return f"{self.redirect_uri}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> dict[str, str]:
        """Return mock access token."""
        return {
            "access_token": "mock_access_token_" + secrets.token_hex(16),
            "token_type": "bearer",
            "scope": "read:user user:email",
        }

    def get_user_info(self, access_token: str) -> dict[str, str | int]:
        """Return mock user info."""
        mock_id = abs(hash(access_token)) % 1000000
        return {
            "id": mock_id,
            "login": f"mockuser_{mock_id}",
            "name": f"Mock User {mock_id}",
            "email": f"mock_{mock_id}@example.com",
        }


@implementer(IOAuthProviderService)
class NullGitHubOAuthClient(_NullOAuthClientBase):
    """
    Null GitHub OAuth client for testing and development ONLY.

    WARNING: This service should NEVER be used in production environments.
    """

    _provider = "github"
    _callback_route = "manage.account.associations.github.callback"


@implementer(IOAuthProviderService)
class NullGitLabOAuthClient(_NullOAuthClientBase):
    """
    Null GitLab OAuth client for testing and development ONLY.

    WARNING: This service should NEVER be used in production environments.
    """

    _provider = "gitlab"
    _callback_route = "manage.account.associations.gitlab.callback"

    def get_user_info(self, access_token: str) -> dict[str, str | int]:
        """Return mock user info with GitLab-specific field names."""
        mock_id = abs(hash(access_token)) % 1000000
        return {
            "id": mock_id,
            "username": f"mockuser_{mock_id}",  # GitLab uses 'username', not 'login'
            "name": f"Mock User {mock_id}",
            "email": f"mock_{mock_id}@example.com",
        }


def generate_state_token() -> str:
    """Generate a secure random state token for CSRF protection."""
    return secrets.token_urlsafe(32)
