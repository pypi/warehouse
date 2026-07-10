# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

from tests.common.constants import REMOTE_ADDR
from tests.common.db.accounts import UserFactory, UserUniqueLoginFactory
from tests.common.db.ip_addresses import IpAddressFactory
from tests.common.db.packaging import ProjectFactory, RoleFactory
from warehouse.accounts.models import UniqueLoginStatus
from warehouse.packaging.models import LifecycleStatus
from warehouse.utils.otp import _get_totp


class TestManageProjects:
    def test_segments_active_and_archived_projects(self, webtest):
        """
        The projects page lists active projects up top and archived
        projects in a separate, clearly labeled section underneath.
        """
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        active_project = ProjectFactory.create(name="active-project")
        RoleFactory.create(user=user, project=active_project, role_name="Owner")
        archived_project = ProjectFactory.create(
            name="archived-project", lifecycle_status=LifecycleStatus.Archived
        )
        RoleFactory.create(user=user, project=archived_project, role_name="Owner")
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

        projects_page = webtest.get("/manage/projects/", status=HTTPStatus.OK)

        assert "Active Projects" in projects_page.text
        assert "Archived Projects" in projects_page.text
        assert "active-project" in projects_page.text
        assert "archived-project" in projects_page.text

    def test_hides_archived_section_when_no_archived_projects(self, webtest):
        """
        The "Archived Projects" section is omitted entirely for a user
        with no archived projects.
        """
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        active_project = ProjectFactory.create(name="only-active-project")
        RoleFactory.create(user=user, project=active_project, role_name="Owner")
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

        projects_page = webtest.get("/manage/projects/", status=HTTPStatus.OK)

        assert "Active Projects" in projects_page.text
        assert "Archived Projects" not in projects_page.text
