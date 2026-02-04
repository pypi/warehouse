# SPDX-License-Identifier: Apache-2.0

import re
import time

from http import HTTPStatus

from urllib3.util import parse_url

from warehouse.accounts.models import UniqueLoginStatus
from warehouse.utils.otp import _get_totp

from ...common.constants import REMOTE_ADDR
from ...common.db.accounts import (
    OAuthAccountAssociationFactory,
    UserFactory,
    UserUniqueLoginFactory,
)
from ...common.db.ip_addresses import IpAddressFactory


class TestAccountAssociations:
    def _login_user(self, webtest, user):
        """Helper method to log in a user with 2FA."""
        # Pre-create confirmed unique login for the test IP
        ip_address = IpAddressFactory.create(ip_address=REMOTE_ADDR)
        UserUniqueLoginFactory.create(
            user=user,
            ip_address=ip_address,
            status=UniqueLoginStatus.CONFIRMED,
        )

        # Login - no device confirmation needed since login is pre-confirmed
        login_page = webtest.get("/account/login/", status=HTTPStatus.OK)
        login_form = login_page.forms["login-form"]
        login_form["username"] = user.username
        login_form["password"] = "password"
        two_factor_page = login_form.submit().follow(status=HTTPStatus.OK)

        two_factor_form = two_factor_page.forms["totp-auth-form"]
        two_factor_form["totp_value"] = (
            _get_totp(user.totp_secret).generate(time.time()).decode()
        )
        two_factor_form.submit().follow(status=HTTPStatus.OK)

    def test_view_account_associations_page(self, webtest):
        """A user can view the account settings page with associations section."""
        # Create a user with a GitHub association
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        OAuthAccountAssociationFactory.create(
            user=user,
            service="github",
            external_username="testuser",
        )

        # Login
        self._login_user(webtest, user)

        # Visit account settings page
        account_page = webtest.get("/manage/account/", status=HTTPStatus.OK)

        # Verify associations section is present
        assert "Account associations" in account_page.text
        assert "testuser" in account_page.text
        assert "github" in account_page.text.lower()

    def test_connect_github_account(self, webtest):
        """A user can connect a GitHub account via OAuth."""
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        # NullGitHubOAuthClient is configured via GITHUB_OAUTH_BACKEND

        # Login
        self._login_user(webtest, user)

        # Click "Connect GitHub" button (initiates OAuth flow)
        # NullGitHubOAuthClient will redirect immediately to callback with mock code
        connect_response = webtest.get(
            "/manage/account/associations/github/connect",
            status=HTTPStatus.SEE_OTHER,
        )

        # Follow the redirect to the callback URL
        # NullGitHubOAuthClient creates a redirect to callback with mock parameters
        # Extract path from absolute URL to preserve webtest session
        parsed_url = parse_url(connect_response.location)
        callback_response = webtest.get(
            parsed_url.path,
            params=parsed_url.query,
            status=HTTPStatus.SEE_OTHER,
        )

        # Follow redirect back to account page
        account_page = callback_response.follow(status=HTTPStatus.OK)

        # Verify association was created
        assert "Account associations" in account_page.text
        assert "mockuser_" in account_page.text

    def test_connect_github_account_invalid_state(self, webtest):
        """OAuth flow rejects requests with invalid state tokens (CSRF protection)."""
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )

        # Login
        self._login_user(webtest, user)

        # Try to access callback directly with invalid state
        callback_response = webtest.get(
            "/manage/account/associations/github/callback",
            params={"code": "test", "state": "invalid"},
            status=HTTPStatus.SEE_OTHER,
        )

        # Should redirect to account page with error
        account_page = callback_response.follow(status=HTTPStatus.OK)
        # Verify no association was created - user has no connected accounts
        assert "You have not connected" in account_page.text

    def test_delete_account_association(self, webtest):
        """A user can delete an account association."""
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        association = OAuthAccountAssociationFactory.create(
            user=user,
            service="github",
            external_username="testuser",
        )

        # Login
        self._login_user(webtest, user)

        # Visit account settings page
        account_page = webtest.get("/manage/account/", status=HTTPStatus.OK)

        # Verify association is present
        assert "testuser" in account_page.text

        # Re-authenticate for dangerous action (simulate confirm prompt)
        # In the real UI, this happens via a modal, but we'll POST directly
        confirm_page = webtest.get("/manage/account/", status=HTTPStatus.OK)
        csrf_token = confirm_page.html.find("input", {"name": "csrf_token"})["value"]

        # Submit delete form
        delete_response = webtest.post(
            "/manage/account/associations/delete",
            {"csrf_token": csrf_token, "association_id": str(association.id)},
            status=HTTPStatus.SEE_OTHER,
        )

        # Follow redirect back to account page
        account_page = delete_response.follow(status=HTTPStatus.OK)

        # Verify association is gone from the associations section
        # (username may still appear in security history showing the removal event)
        assert "You have not connected any external accounts yet" in account_page.text

    def test_cannot_delete_other_users_association(self, webtest):
        """A user cannot delete another user's account association."""
        user1 = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        user2 = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
        )
        association = OAuthAccountAssociationFactory.create(
            user=user2, service="github", external_username="user2github"
        )

        # Login as user1
        self._login_user(webtest, user1)

        # Get CSRF token
        account_page = webtest.get("/manage/account/", status=HTTPStatus.OK)
        csrf_token = account_page.html.find("input", {"name": "csrf_token"})["value"]

        # Try to delete user2's association
        # Should redirect back to account page with error message
        delete_response = webtest.post(
            "/manage/account/associations/delete",
            {"csrf_token": csrf_token, "association_id": str(association.id)},
            status=HTTPStatus.SEE_OTHER,
        )
        delete_response.follow(status=HTTPStatus.OK)

        # Check flash messages for the error
        flash_messages = webtest.get(
            "/_includes/unauthed/flash-messages/", status=HTTPStatus.OK
        )
        error_message = flash_messages.html.find(
            "span", {"class": "notification-bar__message"}
        )
        assert error_message is not None
        assert "Failed to remove account association" in error_message.text

    def test_multiple_github_accounts_per_user(self, webtest):
        """A user can connect multiple GitHub accounts (different external IDs)."""
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )

        # Login
        self._login_user(webtest, user)

        # Connect first GitHub account
        connect_response1 = webtest.get(
            "/manage/account/associations/github/connect",
            status=HTTPStatus.SEE_OTHER,
        )
        # Extract path from absolute URL to preserve webtest session
        parsed_url1 = parse_url(connect_response1.location)
        callback_response1 = webtest.get(
            parsed_url1.path,
            params=parsed_url1.query,
            status=HTTPStatus.SEE_OTHER,
        )
        account_page1 = callback_response1.follow(status=HTTPStatus.OK)
        # Get first mockuser name
        mockuser_match1 = re.search(r"mockuser_\w+", account_page1.text)
        assert mockuser_match1 is not None
        first_mockuser = mockuser_match1.group()

        # Connect second GitHub account
        # NullGitHubOAuthClient generates different mock users each time
        connect_response2 = webtest.get(
            "/manage/account/associations/github/connect",
            status=HTTPStatus.SEE_OTHER,
        )
        # Extract path from absolute URL to preserve webtest session
        parsed_url2 = parse_url(connect_response2.location)
        callback_response2 = webtest.get(
            parsed_url2.path,
            params=parsed_url2.query,
            status=HTTPStatus.SEE_OTHER,
        )
        account_page2 = callback_response2.follow(status=HTTPStatus.OK)

        # Verify both associations appear on the page
        assert first_mockuser in account_page2.text
        mockuser_match2 = re.search(
            r"mockuser_\w+", account_page2.text.replace(first_mockuser, "")
        )
        assert mockuser_match2 is not None  # Found a second different mockuser

    def test_github_oauth_error_response(self, webtest):
        """OAuth flow handles error responses from GitHub."""
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )

        self._login_user(webtest, user)

        # Start OAuth flow to get a valid state token
        connect_response = webtest.get(
            "/manage/account/associations/github/connect", status=HTTPStatus.SEE_OTHER
        )
        # Extract state from the redirect URL
        parsed_url = parse_url(connect_response.location)
        state = parsed_url.query.split("state=")[1].split("&")[0]

        # Simulate OAuth error response with valid state
        callback_response = webtest.get(
            "/manage/account/associations/github/callback",
            params={
                "state": state,
                "error": "access_denied",
                "error_description": "User declined",
            },
            status=HTTPStatus.SEE_OTHER,
        )
        callback_response.follow(status=HTTPStatus.OK)

        # Check flash messages for the error
        flash_messages = webtest.get(
            "/_includes/unauthed/flash-messages/", status=HTTPStatus.OK
        )
        error_message = flash_messages.html.find(
            "span", {"class": "notification-bar__message"}
        )
        assert error_message is not None
        assert "GitHub OAuth failed" in error_message.text
        assert "User declined" in error_message.text

    def test_github_oauth_missing_code(self, webtest):
        """OAuth flow handles missing authorization code."""
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )

        self._login_user(webtest, user)

        # Start OAuth flow to get a valid state token
        connect_response = webtest.get(
            "/manage/account/associations/github/connect",
            status=HTTPStatus.SEE_OTHER,
        )
        # Extract state from the redirect URL
        parsed_url = parse_url(connect_response.location)
        state = parsed_url.query.split("state=")[1].split("&")[0]

        # Call callback with valid state but no code
        callback_response = webtest.get(
            "/manage/account/associations/github/callback",
            params={"state": state},
            status=HTTPStatus.SEE_OTHER,
        )
        callback_response.follow(status=HTTPStatus.OK)

        # Check flash messages for the error
        flash_messages = webtest.get(
            "/_includes/unauthed/flash-messages/",
            status=HTTPStatus.OK,
        )
        error_message = flash_messages.html.find(
            "span", {"class": "notification-bar__message"}
        )
        assert error_message is not None
        assert "No authorization code received from GitHub" in error_message.text
