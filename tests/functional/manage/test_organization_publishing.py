# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

import pytest
import responses

from tests.common.constants import REMOTE_ADDR
from tests.common.db.accounts import UserFactory, UserUniqueLoginFactory
from tests.common.db.organizations import OrganizationFactory, OrganizationRoleFactory
from warehouse.accounts.models import UniqueLoginStatus
from warehouse.organizations.models import OrganizationRoleType
from warehouse.utils.otp import _get_totp


@pytest.mark.usefixtures("_enable_all_oidc_providers")
class TestManageOrganizationPublishing:
    @responses.activate
    def test_add_pending_github_publisher_to_organization(self, webtest):
        """
        An authenticated user who is an organization owner can add a pending
        GitHub trusted publisher to their organization.
        """
        # Arrange: Create a user with an organization
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        UserUniqueLoginFactory.create(
            user=user, ip_address=REMOTE_ADDR, status=UniqueLoginStatus.CONFIRMED
        )
        organization = OrganizationFactory.create(name="test-organization")
        OrganizationRoleFactory.create(
            user=user,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

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

        # Navigate to organization publishing page
        publishing_page = webtest.get(
            f"/manage/organization/{organization.normalized_name}/publishing/",
            status=HTTPStatus.OK,
        )

        # Get logged-in CSRF token
        logged_in_csrf_token = publishing_page.html.find(
            "input", {"name": "csrf_token"}
        )["value"]

        # Fill out the GitHub pending publisher form
        github_form = publishing_page.forms["pending-github-publisher-form"]
        github_form["csrf_token"] = logged_in_csrf_token
        github_form["project_name"] = "test-org-project"
        github_form["owner"] = "test-owner"
        github_form["repository"] = "test-repo"
        github_form["workflow_filename"] = "release.yml"
        github_form["environment"] = ""  # Optional field

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
        assert "Registered a new pending publisher" in success_message.text
        assert "test-org-project" in success_message.text
        assert organization.name in success_message.text

    def test_add_pending_gitlab_publisher_to_organization(self, webtest):
        """
        An authenticated user who is an organization owner can add a pending
        GitLab trusted publisher to their organization.
        """
        # Arrange: Create a user with an organization
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        UserUniqueLoginFactory.create(
            user=user, ip_address=REMOTE_ADDR, status=UniqueLoginStatus.CONFIRMED
        )
        organization = OrganizationFactory.create(name="test-organization")
        OrganizationRoleFactory.create(
            user=user,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
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

        # Navigate to organization publishing page
        publishing_page = webtest.get(
            f"/manage/organization/{organization.normalized_name}/publishing/",
            status=HTTPStatus.OK,
        )

        # Get logged-in CSRF token
        logged_in_csrf_token = publishing_page.html.find(
            "input", {"name": "csrf_token"}
        )["value"]

        # Fill out the GitLab pending publisher form
        gitlab_form = publishing_page.forms["pending-gitlab-publisher-form"]
        gitlab_form["csrf_token"] = logged_in_csrf_token
        gitlab_form["project_name"] = "test-org-gitlab-project"
        gitlab_form["namespace"] = "test-namespace"
        gitlab_form["project"] = "test-project"
        gitlab_form["workflow_filepath"] = ".gitlab-ci.yml"
        gitlab_form["environment"] = ""  # Optional field
        # issuer_url is a hidden field with default value

        # Submit the form, redirects back to the same page on success
        response = gitlab_form.submit(status=HTTPStatus.SEE_OTHER)
        response.follow(status=HTTPStatus.OK)

        # Assert: Verify success
        flash_messages = webtest.get(
            "/_includes/unauthed/flash-messages/", status=HTTPStatus.OK
        )
        success_message = flash_messages.html.find(
            "span", {"class": "notification-bar__message"}
        )
        assert success_message is not None
        assert "Registered a new pending publisher" in success_message.text
        assert "test-org-gitlab-project" in success_message.text
        assert organization.name in success_message.text

    def test_add_pending_google_publisher_to_organization(self, webtest):
        """
        An authenticated user who is an organization owner can add a pending
        Google trusted publisher to their organization.
        """
        # Arrange: Create a user with an organization
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        UserUniqueLoginFactory.create(
            user=user, ip_address=REMOTE_ADDR, status=UniqueLoginStatus.CONFIRMED
        )
        organization = OrganizationFactory.create(name="test-organization")
        OrganizationRoleFactory.create(
            user=user,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
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

        # Navigate to organization publishing page
        publishing_page = webtest.get(
            f"/manage/organization/{organization.normalized_name}/publishing/",
            status=HTTPStatus.OK,
        )

        # Get logged-in CSRF token
        logged_in_csrf_token = publishing_page.html.find(
            "input", {"name": "csrf_token"}
        )["value"]

        # Fill out the Google pending publisher form
        google_form = publishing_page.forms["pending-google-publisher-form"]
        google_form["csrf_token"] = logged_in_csrf_token
        google_form["project_name"] = "test-org-google-project"
        google_form["email"] = "test@example.com"
        google_form["sub"] = ""  # Optional field

        # Submit the form, redirects back to the same page on success
        response = google_form.submit(status=HTTPStatus.SEE_OTHER)
        response.follow(status=HTTPStatus.OK)

        # Assert: Verify success
        flash_messages = webtest.get(
            "/_includes/unauthed/flash-messages/", status=HTTPStatus.OK
        )
        success_message = flash_messages.html.find(
            "span", {"class": "notification-bar__message"}
        )
        assert success_message is not None
        assert "Registered a new pending publisher" in success_message.text
        assert "test-org-google-project" in success_message.text
        assert organization.name in success_message.text

    @responses.activate
    def test_add_pending_activestate_publisher_to_organization(self, webtest):
        """
        An authenticated user who is an organization owner can add a pending
        ActiveState trusted publisher to their organization.
        """
        # Arrange: Create a user with an organization
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        UserUniqueLoginFactory.create(
            user=user, ip_address=REMOTE_ADDR, status=UniqueLoginStatus.CONFIRMED
        )
        organization = OrganizationFactory.create(name="test-organization")
        OrganizationRoleFactory.create(
            user=user,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        # Mock ActiveState API for organization and actor validation
        # The form makes two sequential API calls:
        # 1. Organization validation (validate_organization method)
        # 2. Actor validation (validate_actor method)
        responses.add(
            responses.POST,
            "https://platform.activestate.com/graphql/v1/graphql",
            json={"data": {"organizations": [{"added": "2020-01-01"}]}},
            status=200,
        )
        responses.add(
            responses.POST,
            "https://platform.activestate.com/graphql/v1/graphql",
            json={"data": {"users": [{"user_id": "test-user-id"}]}},
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

        # Navigate to organization publishing page
        publishing_page = webtest.get(
            f"/manage/organization/{organization.normalized_name}/publishing/",
            status=HTTPStatus.OK,
        )

        # Get logged-in CSRF token
        logged_in_csrf_token = publishing_page.html.find(
            "input", {"name": "csrf_token"}
        )["value"]

        # Fill out the ActiveState pending publisher form
        activestate_form = publishing_page.forms["pending-activestate-publisher-form"]
        activestate_form["csrf_token"] = logged_in_csrf_token
        activestate_form["project_name"] = "test-org-activestate-project"
        activestate_form["organization"] = "test-activestate-org"
        activestate_form["project"] = "test-activestate-project"
        activestate_form["actor"] = "test-actor"

        # Submit the form, redirects back to the same page on success
        response = activestate_form.submit(status=HTTPStatus.SEE_OTHER)
        response.follow(status=HTTPStatus.OK)

        # Assert: Verify success
        flash_messages = webtest.get(
            "/_includes/unauthed/flash-messages/", status=HTTPStatus.OK
        )
        success_message = flash_messages.html.find(
            "span", {"class": "notification-bar__message"}
        )
        assert success_message is not None
        assert "Registered a new pending publisher" in success_message.text
        assert "test-org-activestate-project" in success_message.text
        assert organization.name in success_message.text
