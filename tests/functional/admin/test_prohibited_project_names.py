# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

from tests.common.constants import REMOTE_ADDR
from tests.common.db.accounts import UserFactory, UserUniqueLoginFactory
from tests.common.db.ip_addresses import IpAddressFactory
from tests.common.db.organizations import OrganizationFactory, OrganizationRoleFactory
from tests.common.db.packaging import ProhibitedProjectFactory
from warehouse.accounts.models import UniqueLoginStatus
from warehouse.organizations.models import OrganizationProject
from warehouse.packaging.models import Project
from warehouse.utils.otp import _get_totp


class TestReleaseProhibitedProjectName:
    def _login_admin(self, webtest, user):
        """Log in a superuser with 2FA and a pre-confirmed IP."""
        ip_address = IpAddressFactory.create(ip_address=REMOTE_ADDR)
        UserUniqueLoginFactory.create(
            user=user,
            ip_address=ip_address,
            status=UniqueLoginStatus.CONFIRMED,
        )

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

    def test_release_to_organization_redirects_to_project_detail(self, webtest):
        """
        Releasing a prohibited name to an organization returns a 303 to the new
        project's admin detail page, and following that redirect resolves (the
        project is committed before the browser follows it, so it is not a 404).
        """
        admin = UserFactory.create(
            is_superuser=True,
            with_verified_primary_email=True,
            clear_pwd="password",
        )
        self._login_admin(webtest, admin)

        organization = OrganizationFactory.create(name="release-org")
        OrganizationRoleFactory.create(organization=organization, user=admin)
        ProhibitedProjectFactory.create(name="releasable")

        list_page = webtest.get(
            "/admin/prohibited_project_names/", status=HTTPStatus.OK
        )
        csrf_token = list_page.html.find("input", {"name": "csrf_token"})["value"]

        response = webtest.post(
            "/admin/prohibited_project_names/release/",
            {
                "csrf_token": csrf_token,
                "project_name": "releasable",
                "organization_name": "release-org",
            },
            status=HTTPStatus.SEE_OTHER,
        )
        assert response.headers["Location"].endswith("/admin/projects/releasable/")

        detail_page = response.follow(status=HTTPStatus.OK)
        assert "releasable" in detail_page.text

        db_sess = webtest.extra_environ["warehouse.db_session"]
        project = db_sess.query(Project).filter(Project.name == "releasable").one()
        assert (
            db_sess.query(OrganizationProject)
            .filter(
                OrganizationProject.organization == organization,
                OrganizationProject.project == project,
            )
            .count()
            == 1
        )

    def test_release_error_redirects_to_list(self, webtest):
        """
        An error path (here, an unknown organization) returns a 303 whose target
        is the list page, not the POST-only release route. Following it resolves
        (200) rather than 404, and the flashed error is shown.
        """
        admin = UserFactory.create(
            is_superuser=True,
            with_verified_primary_email=True,
            clear_pwd="password",
        )
        self._login_admin(webtest, admin)

        ProhibitedProjectFactory.create(name="releasable")

        list_page = webtest.get(
            "/admin/prohibited_project_names/", status=HTTPStatus.OK
        )
        csrf_token = list_page.html.find("input", {"name": "csrf_token"})["value"]

        response = webtest.post(
            "/admin/prohibited_project_names/release/",
            {
                "csrf_token": csrf_token,
                "project_name": "releasable",
                "organization_name": "does-not-exist",
            },
            status=HTTPStatus.SEE_OTHER,
        )
        assert response.headers["Location"].endswith("/admin/prohibited_project_names/")

        followed = response.follow(status=HTTPStatus.OK)
        assert "Unknown organization 'does-not-exist'" in followed.html.get_text()
