# SPDX-License-Identifier: Apache-2.0

import urllib.parse

from http import HTTPStatus

import pytest
import responses

from requests.exceptions import HTTPError
from urllib3.util import parse_url
from zope.interface.verify import verifyClass

from warehouse.accounts.oauth import (
    GitHubOAuthClient,
    IOAuthProviderService,
    NullOAuthClient,
    generate_state_token,
)


class TestIOAuthProviderService:
    def test_verify_interface(self):
        assert verifyClass(IOAuthProviderService, GitHubOAuthClient)
        assert verifyClass(IOAuthProviderService, NullOAuthClient)


class TestGenerateStateToken:
    def test_generates_token(self):
        token = generate_state_token()
        assert isinstance(token, str)
        # token_urlsafe(32) generates a URL-safe string from 32 random bytes
        # Base64 encoding of 32 bytes is 43 characters (with padding)
        assert len(token) >= 40  # Allow some flexibility for URL-safe encoding

    def test_generates_unique_tokens(self):
        token1 = generate_state_token()
        token2 = generate_state_token()
        assert token1 != token2


class TestGitHubOAuthClient:
    def test_initialization(self):
        client = GitHubOAuthClient(
            client_id="test_id",
            client_secret="test_secret",
            redirect_uri="http://localhost/callback",
        )
        assert client.client_id == "test_id"
        assert client.client_secret == "test_secret"
        assert client.redirect_uri == "http://localhost/callback"

    def test_create_service(self, mocker):
        request = mocker.Mock()
        request.registry.settings = {
            "github.oauth.client_id": "test_id",
            "github.oauth.client_secret": "test_secret",
        }
        request.route_url.return_value = "http://localhost/callback"
        context = None

        client = GitHubOAuthClient.create_service(context, request)

        assert isinstance(client, GitHubOAuthClient)
        assert client.client_id == "test_id"
        assert client.client_secret == "test_secret"
        assert client.redirect_uri == "http://localhost/callback"
        request.route_url.assert_called_once_with(
            "manage.account.associations.github.callback"
        )

    def test_generate_authorize_url_no_scopes(self):
        client = GitHubOAuthClient(
            client_id="test_id",
            client_secret="test_secret",
            redirect_uri="http://localhost/callback",
        )
        state = "test_state_token"

        url = client.generate_authorize_url(state)

        parsed = parse_url(url)
        assert parsed.scheme == "https"
        assert parsed.host == "github.com"
        assert parsed.path == "/login/oauth/authorize"

        query_params = urllib.parse.parse_qs(parsed.query)
        assert query_params["client_id"] == ["test_id"]
        assert query_params["redirect_uri"] == ["http://localhost/callback"]
        assert query_params["state"] == ["test_state_token"]
        assert query_params["scope"] == ["read:user user:email"]

    def test_generate_authorize_url_with_scopes(self):
        client = GitHubOAuthClient(
            client_id="test_id",
            client_secret="test_secret",
            redirect_uri="http://localhost/callback",
        )
        state = "test_state_token"
        scopes = ["repo", "user"]

        url = client.generate_authorize_url(state, scopes=scopes)

        parsed = parse_url(url)
        query_params = urllib.parse.parse_qs(parsed.query)
        assert query_params["scope"] == ["repo user"]

    @responses.activate
    def test_exchange_code_for_token_success(self):
        response_data = {
            "access_token": "gho_test_token",
            "token_type": "bearer",
            "scope": "read:user,user:email",
        }
        responses.add(
            responses.POST,
            GitHubOAuthClient.TOKEN_URL,
            json=response_data,
            status=HTTPStatus.OK,
        )

        client = GitHubOAuthClient(
            client_id="test_id",
            client_secret="test_secret",
            redirect_uri="http://localhost/callback",
        )

        result = client.exchange_code_for_token("test_code")

        assert result == response_data
        assert len(responses.calls) == 1

        # Verify the request payload
        request_body = dict(urllib.parse.parse_qsl(responses.calls[0].request.body))
        assert request_body["client_id"] == "test_id"
        assert request_body["client_secret"] == "test_secret"
        assert request_body["code"] == "test_code"
        assert request_body["redirect_uri"] == "http://localhost/callback"
        assert responses.calls[0].request.headers["Accept"] == "application/json"

    @responses.activate
    def test_exchange_code_for_token_http_error(self):
        responses.add(
            responses.POST,
            GitHubOAuthClient.TOKEN_URL,
            json={"error": "bad_verification_code"},
            status=HTTPStatus.BAD_REQUEST,
        )

        client = GitHubOAuthClient(
            client_id="test_id",
            client_secret="test_secret",
            redirect_uri="http://localhost/callback",
        )

        with pytest.raises(HTTPError):
            client.exchange_code_for_token("test_code")

    @responses.activate
    def test_get_user_info_success(self):
        user_data = {
            "id": 12345,
            "login": "testuser",
            "name": "Test User",
            "email": "test@example.com",
        }
        responses.add(
            responses.GET,
            GitHubOAuthClient.USER_API_URL,
            json=user_data,
            status=HTTPStatus.OK,
        )

        client = GitHubOAuthClient(
            client_id="test_id",
            client_secret="test_secret",
            redirect_uri="http://localhost/callback",
        )

        result = client.get_user_info("test_access_token")

        assert result == user_data
        assert len(responses.calls) == 1
        assert (
            responses.calls[0].request.headers["Authorization"]
            == "Bearer test_access_token"
        )
        assert responses.calls[0].request.headers["Accept"] == "application/json"

    @responses.activate
    def test_get_user_info_http_error(self):
        responses.add(
            responses.GET,
            GitHubOAuthClient.USER_API_URL,
            json={"message": "Bad credentials"},
            status=HTTPStatus.UNAUTHORIZED,
        )

        client = GitHubOAuthClient(
            client_id="test_id",
            client_secret="test_secret",
            redirect_uri="http://localhost/callback",
        )

        with pytest.raises(HTTPError):
            client.get_user_info("test_access_token")


class TestNullOAuthClient:
    def test_initialization(self):
        client = NullOAuthClient(redirect_uri="http://localhost/callback")
        assert client.client_id == "null"
        assert client.client_secret == "null"
        assert client.redirect_uri == "http://localhost/callback"

    def test_initialization_with_params(self):
        client = NullOAuthClient(
            client_id="custom_id",
            client_secret="custom_secret",
            redirect_uri="http://localhost/callback",
        )
        assert client.client_id == "custom_id"
        assert client.client_secret == "custom_secret"

    def test_create_service(self, mocker):
        request = mocker.Mock()
        request.route_url.return_value = "http://localhost/callback"
        context = None

        client = NullOAuthClient.create_service(context, request)

        assert isinstance(client, NullOAuthClient)
        assert client.redirect_uri == "http://localhost/callback"
        request.route_url.assert_called_once_with(
            "manage.account.associations.github.callback"
        )

    def test_generate_authorize_url(self):
        client = NullOAuthClient(redirect_uri="http://localhost/callback")
        state = "test_state_token"

        url = client.generate_authorize_url(state)

        parsed = parse_url(url)
        assert parsed.scheme == "http"
        assert parsed.host == "localhost"
        assert parsed.path == "/callback"

        query_params = urllib.parse.parse_qs(parsed.query)
        assert query_params["code"] == ["mock_authorization_code"]
        assert query_params["state"] == ["test_state_token"]

    def test_generate_authorize_url_ignores_scopes(self):
        client = NullOAuthClient(redirect_uri="http://localhost/callback")
        state = "test_state_token"

        url = client.generate_authorize_url(state, scopes=["repo", "user"])

        # Should work the same regardless of scopes
        parsed = parse_url(url)
        query_params = urllib.parse.parse_qs(parsed.query)
        assert query_params["code"] == ["mock_authorization_code"]
        assert query_params["state"] == ["test_state_token"]

    def test_exchange_code_for_token(self):
        client = NullOAuthClient(redirect_uri="http://localhost/callback")

        result = client.exchange_code_for_token("test_code")

        assert isinstance(result, dict)
        assert "access_token" in result
        assert result["access_token"].startswith("mock_access_token_")
        assert result["token_type"] == "bearer"
        assert result["scope"] == "read:user user:email"

    def test_exchange_code_for_token_unique_tokens(self):
        client = NullOAuthClient(redirect_uri="http://localhost/callback")

        result1 = client.exchange_code_for_token("test_code")
        result2 = client.exchange_code_for_token("test_code")

        # Each call should generate a unique token
        assert result1["access_token"] != result2["access_token"]

    def test_get_user_info(self):
        client = NullOAuthClient(redirect_uri="http://localhost/callback")

        result = client.get_user_info("mock_access_token_abc123")

        assert isinstance(result, dict)
        assert "id" in result
        assert "login" in result
        assert "name" in result
        assert "email" in result
        assert isinstance(result["id"], int)
        assert result["id"] > 0
        assert result["login"].startswith("mockuser_")
        assert result["name"].startswith("Mock User ")
        assert result["email"].endswith("@example.com")

    def test_get_user_info_consistent_for_same_token(self):
        client = NullOAuthClient(redirect_uri="http://localhost/callback")

        result1 = client.get_user_info("same_token")
        result2 = client.get_user_info("same_token")

        # Same token should return same user data
        assert result1 == result2

    def test_get_user_info_different_for_different_tokens(self):
        client = NullOAuthClient(redirect_uri="http://localhost/callback")

        result1 = client.get_user_info("token_one")
        result2 = client.get_user_info("token_two")

        # Different tokens should return different user data
        assert result1["id"] != result2["id"]
        assert result1["login"] != result2["login"]
