# SPDX-License-Identifier: Apache-2.0

import json
import time

from http import HTTPStatus

import jwt
import pytest
import responses

from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import algorithms
from pyramid_services import IServiceRegistry, ProxyFactory

from tests.common.constants import REMOTE_ADDR
from tests.common.db.accounts import UserFactory, UserUniqueLoginFactory
from tests.common.db.ip_addresses import IpAddressFactory
from tests.common.db.packaging import ProjectFactory, RoleFactory
from warehouse.accounts.models import UniqueLoginStatus
from warehouse.oidc import interfaces as oidc_interfaces, services as oidc_services
from warehouse.oidc.models import BUILDKITE_OIDC_ISSUER_URL
from warehouse.utils.otp import _get_totp


class _InMemoryOIDCPublisherService(oidc_services.OIDCPublisherService):
    keysets = {}

    def _store_keyset(self, issuer_url, keys):
        self.keysets[issuer_url] = keys

    def _get_keyset(self, issuer_url):
        return self.keysets.get(issuer_url, {}), False


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
        ip_address = IpAddressFactory.create(ip_address=REMOTE_ADDR)
        UserUniqueLoginFactory.create(
            user=user, ip_address=ip_address, status=UniqueLoginStatus.CONFIRMED
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
        ip_address = IpAddressFactory.create(ip_address=REMOTE_ADDR)
        UserUniqueLoginFactory.create(
            user=user, ip_address=ip_address, status=UniqueLoginStatus.CONFIRMED
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

    @responses.activate
    def test_buildkite_publisher_mints_api_token(
        self, webtest, app_config_dbsession_from_env
    ):
        """A Buildkite publisher pins IDs on first use and enforces them."""
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        project = ProjectFactory.create(name="buildkite-project")
        RoleFactory.create(user=user, project=project, role_name="Owner")
        ip_address = IpAddressFactory.create(ip_address=REMOTE_ADDR)
        UserUniqueLoginFactory.create(
            user=user, ip_address=ip_address, status=UniqueLoginStatus.CONFIRMED
        )

        login_page = webtest.get("/account/login/", status=HTTPStatus.OK)
        login_form = login_page.forms["login-form"]
        csrf_token = login_form["csrf_token"].value
        login_form["username"] = user.username
        login_form["password"] = "password"
        two_factor_page = login_form.submit().follow(status=HTTPStatus.OK)
        two_factor_form = two_factor_page.forms["totp-auth-form"]
        two_factor_form["csrf_token"] = csrf_token
        two_factor_form["totp_value"] = (
            _get_totp(user.totp_secret).generate(time.time()).decode()
        )
        two_factor_form.submit().follow(status=HTTPStatus.OK)

        publishing_page = webtest.get(
            f"/manage/project/{project.name}/settings/publishing/",
            status=HTTPStatus.OK,
        )
        buildkite_form = publishing_page.forms["buildkite-publisher-form"]
        buildkite_form["organization_slug"] = "acme"
        buildkite_form["pipeline_slug"] = "widgets"
        buildkite_form["build_branch"] = "main"
        buildkite_form["step_key"] = "publish"
        registered_page = buildkite_form.submit(status=HTTPStatus.SEE_OTHER).follow(
            status=HTTPStatus.OK
        )
        assert registered_page.text.count("Not yet pinned") == 2

        now = int(time.time())
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_jwk = json.loads(
            algorithms.RSAAlgorithm.to_jwk(private_key.public_key())
        )
        public_jwk.update({"alg": "RS256", "kid": "buildkite-test", "use": "sig"})

        jwks_url = f"{BUILDKITE_OIDC_ISSUER_URL}/.well-known/jwks"
        responses.add(
            responses.GET,
            f"{BUILDKITE_OIDC_ISSUER_URL}/.well-known/openid-configuration",
            json={"jwks_uri": jwks_url},
        )
        responses.add(responses.GET, jwks_url, json={"keys": [public_jwk]})

        token_claims = {
            "iss": BUILDKITE_OIDC_ISSUER_URL,
            "sub": (
                "organization:acme:pipeline:widgets:ref:refs/heads/main:"
                "commit:abc123:step:publish"
            ),
            "aud": "pypi",
            "iat": now,
            "nbf": now,
            "exp": now + 300,
            "organization_slug": "acme",
            "organization_id": "00000000-1111-2222-3333-444444444444",
            "pipeline_slug": "widgets",
            "pipeline_id": "11111111-2222-3333-4444-555555555555",
            "build_number": 42,
            "build_branch": "main",
            "build_commit": "abc123",
            "step_key": "publish",
            "job_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "agent_id": "ffffffff-1111-2222-3333-444444444444",
            "runner_environment": "buildkite-hosted",
            "build_source": "webhook",
        }

        oidc_token = jwt.encode(
            token_claims,
            private_key,
            algorithm="RS256",
            headers={"kid": "buildkite-test"},
        )

        service_registry = app_config_dbsession_from_env.registry.getUtility(
            IServiceRegistry
        )
        original_factory = service_registry.find_factory(
            oidc_interfaces.IOIDCPublisherService, name="buildkite"
        )
        service_factory = oidc_services.OIDCPublisherServiceFactory(
            publisher="buildkite",
            issuer_url=BUILDKITE_OIDC_ISSUER_URL,
            service_class=_InMemoryOIDCPublisherService,
        )
        service_registry.register_factory(
            ProxyFactory(service_factory),
            oidc_interfaces.IOIDCPublisherService,
            name="buildkite",
        )
        _InMemoryOIDCPublisherService.keysets.clear()
        try:
            response = webtest.post_json(
                "/_/oidc/mint-token",
                {"token": oidc_token},
                status=HTTPStatus.OK,
            )
        finally:
            service_registry.register_factory(
                original_factory,
                oidc_interfaces.IOIDCPublisherService,
                name="buildkite",
            )

        assert response.json["success"] is True
        assert response.json["token"].startswith("pypi-")
        assert response.json["expires"] > now

        pinned_page = webtest.get(
            f"/manage/project/{project.name}/settings/publishing/",
            status=HTTPStatus.OK,
        )
        assert token_claims["organization_id"] in pinned_page
        assert token_claims["pipeline_id"] in pinned_page

        missing_claims = token_claims.copy()
        missing_claims.pop("organization_id")
        missing_token = jwt.encode(
            missing_claims,
            private_key,
            algorithm="RS256",
            headers={"kid": "buildkite-test"},
        )
        missing_response = webtest.post_json(
            "/_/oidc/mint-token",
            {"token": missing_token},
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
        assert (
            "--claim organization_id"
            in missing_response.json["errors"][0]["description"]
        )

        mismatched_claims = token_claims | {"pipeline_id": "different-pipeline"}
        mismatched_token = jwt.encode(
            mismatched_claims,
            private_key,
            algorithm="RS256",
            headers={"kid": "buildkite-test"},
        )
        mismatched_response = webtest.post_json(
            "/_/oidc/mint-token",
            {"token": mismatched_token},
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
        assert "does not match" in mismatched_response.json["errors"][0]["description"]
        assert [call.request.url for call in responses.calls] == [
            f"{BUILDKITE_OIDC_ISSUER_URL}/.well-known/openid-configuration",
            jwks_url,
        ]
