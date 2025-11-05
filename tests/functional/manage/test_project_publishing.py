# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

import pytest
import responses

from tests.common.db.accounts import UserFactory
from tests.common.db.packaging import ProjectFactory, RoleFactory
from warehouse.utils.otp import _get_totp


@pytest.mark.usefixtures("_enable_all_oidc_providers")
class TestManageProjectPublishing:
    @responses.activate
    def test_add_github_publisher_to_existing_project(self, webtest):
        """
        An authenticated user with project ownership can add a GitHub
        trusted publisher to their existing project.
        """
        # Arrange: Create a user with a project
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        project = ProjectFactory.create(name="existing-project")
        RoleFactory.create(user=user, project=project, role_name="Owner")

        # Mock GitHub API for owner validation
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

        # Navigate to project publishing settings page
        publishing_page = webtest.get(
            f"/manage/project/{project.name}/settings/publishing/",
            status=HTTPStatus.OK,
        )

        # Get logged-in CSRF token
        logged_in_csrf_token = publishing_page.html.find(
            "input", {"name": "csrf_token"}
        )["value"]

        # Fill out the GitHub publisher form
        github_form = publishing_page.forms["github-publisher-form"]
        github_form["csrf_token"] = logged_in_csrf_token
        github_form["owner"] = "test-owner"
        github_form["repository"] = "test-repo"
        github_form["workflow_filename"] = "release.yml"
        # Note: No project_name field - this is for an existing project

        # Submit the form, redirects back to the same page on success
        response = github_form.submit(status=HTTPStatus.SEE_OTHER)
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
        assert "Added" in success_message.text
        assert "release.yml" in success_message.text
        assert "existing-project" in success_message.text

    def test_add_gitlab_publisher_to_existing_project(self, webtest):
        """
        An authenticated user with project ownership can add a GitLab
        trusted publisher to their existing project.
        """
        # Arrange: Create a user with a project
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        project = ProjectFactory.create(name="gitlab-project")
        RoleFactory.create(user=user, project=project, role_name="Owner")

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

        # Navigate to project publishing settings page
        publishing_page = webtest.get(
            f"/manage/project/{project.name}/settings/publishing/",
            status=HTTPStatus.OK,
        )

        # Get logged-in CSRF token
        logged_in_csrf_token = publishing_page.html.find(
            "input", {"name": "csrf_token"}
        )["value"]

        # Fill out the GitLab publisher form
        gitlab_form = publishing_page.forms["gitlab-publisher-form"]
        gitlab_form["csrf_token"] = logged_in_csrf_token
        gitlab_form["namespace"] = "gitlab-namespace"
        gitlab_form["project"] = "gitlab-repo"
        gitlab_form["workflow_filepath"] = ".gitlab-ci.yml"
        # Note: issuer_url defaults to https://gitlab.com when not specified

        # Submit the form
        response = gitlab_form.submit(status=HTTPStatus.SEE_OTHER)
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
        assert "Added" in success_message.text
        assert ".gitlab-ci.yml" in success_message.text
        assert "gitlab-project" in success_message.text
