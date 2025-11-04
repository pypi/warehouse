# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

import pytest
import responses

from tests.common.db.accounts import UserFactory
from warehouse.utils.otp import _get_totp


@pytest.mark.usefixtures("_enable_all_oidc_providers")
class TestManageAccountPublishing:
    @responses.activate
    def test_add_pending_github_publisher_succeeds(self, webtest):
        """
        An authenticated user add a new pending GitHub publisher
        via the form on their account publishing page.
        """
        # Arrange: Create a user with verified email
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        # Create a response from GitHub API for owner details
        # during form submission validation.
        responses.add(
            responses.GET,
            "https://api.github.com/users/test-owner",
            json={
                "id": 123456,
                "login": "test-owner",
            },
            status=200,
        )

        # Act: Log in
        login_page = webtest.get("/account/login/", status=HTTPStatus.OK)
        login_form = login_page.forms["login-form"]
        csrf_token = login_form["csrf_token"].value
        login_form["username"] = user.username
        login_form["password"] = "password"
        # Handle 2FA
        two_factor_page = login_form.submit().follow(status=HTTPStatus.OK)
        two_factor_form = two_factor_page.forms["totp-auth-form"]
        two_factor_form["csrf_token"] = csrf_token
        two_factor_form["totp_value"] = (
            _get_totp(user.totp_secret).generate(time.time()).decode()
        )
        two_factor_form.submit().follow(status=HTTPStatus.OK)

        # Navigate to publishing page
        publishing_page = webtest.get(
            "/manage/account/publishing/", status=HTTPStatus.OK
        )

        # Get logged-in CSRF token
        logged_in_csrf_token = publishing_page.html.find(
            "input", {"name": "csrf_token"}
        )["value"]

        # Fill out the GitHub publisher form
        github_form = publishing_page.forms["pending-github-publisher-form"]
        github_form["csrf_token"] = logged_in_csrf_token
        github_form["project_name"] = "test-project"
        github_form["owner"] = "test-owner"
        github_form["repository"] = "test-repo"
        github_form["workflow_filename"] = "release.yml"

        # Submit the form, redirects back to the same page on success
        response = github_form.submit(status=HTTPStatus.SEE_OTHER)
        # Follow the redirect and verify the page loads
        response.follow(status=HTTPStatus.OK)

        # Assert: Verify success
        # Check flash messages via the JavaScript endpoint
        # Note: Despite the "unauthed" path, this endpoint shows session flash
        # messages for any user (authed or unauthed). The name is misleading.
        # WebTest maintains session cookies, so the flash message is available.
        flash_messages = webtest.get(
            "/_includes/unauthed/flash-messages/", status=HTTPStatus.OK
        )
        success_message = flash_messages.html.find(
            "span", {"class": "notification-bar__message"}
        )
        assert success_message is not None
        assert "Registered a new pending publisher" in success_message.text
        assert "test-project" in success_message.text

    def test_add_pending_gitlab_publisher_succeeds(self, webtest):
        """
        An authenticated user can add a new Pending GitLab publisher
        via the form on their account publishing page.
        """
        # Arrange: Create a user with verified email
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )

        # Act: Log in
        login_page = webtest.get("/account/login/", status=HTTPStatus.OK)
        login_form = login_page.forms["login-form"]
        csrf_token = login_form["csrf_token"].value
        login_form["username"] = user.username
        login_form["password"] = "password"
        # Handle 2FA
        two_factor_page = login_form.submit().follow(status=HTTPStatus.OK)
        two_factor_form = two_factor_page.forms["totp-auth-form"]
        two_factor_form["csrf_token"] = csrf_token
        two_factor_form["totp_value"] = (
            _get_totp(user.totp_secret).generate(time.time()).decode()
        )
        two_factor_form.submit().follow(status=HTTPStatus.OK)

        # Navigate to publishing page
        publishing_page = webtest.get(
            "/manage/account/publishing/", status=HTTPStatus.OK
        )

        # Get logged-in CSRF token
        logged_in_csrf_token = publishing_page.html.find(
            "input", {"name": "csrf_token"}
        )["value"]

        # Fill out the GitLab publisher form
        gitlab_form = publishing_page.forms["pending-gitlab-publisher-form"]
        gitlab_form["csrf_token"] = logged_in_csrf_token
        gitlab_form["project_name"] = "gitlab-project"
        gitlab_form["namespace"] = "gitlab-namespace"
        gitlab_form["project"] = "gitlab-project"
        gitlab_form["workflow_filepath"] = "ci.yml"

        # Submit the form
        response = gitlab_form.submit(status=HTTPStatus.SEE_OTHER)
        # Follow the redirect and verify the page loads
        response.follow(status=HTTPStatus.OK)

        # Assert: Verify success
        # Check flash messages via the JavaScript endpoint
        flash_messages = webtest.get(
            "/_includes/unauthed/flash-messages/", status=HTTPStatus.OK
        )
        success_message = flash_messages.html.find(
            "span", {"class": "notification-bar__message"}
        )
        assert success_message is not None
        assert "Registered a new pending publisher" in success_message.text
        assert "gitlab-project" in success_message.text
