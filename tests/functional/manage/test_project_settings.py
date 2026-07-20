# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

from tests.common.constants import REMOTE_ADDR
from tests.common.db.accounts import UserFactory, UserUniqueLoginFactory
from tests.common.db.ip_addresses import IpAddressFactory
from tests.common.db.packaging import ProjectFactory, RoleFactory
from warehouse.accounts.models import UniqueLoginStatus
from warehouse.packaging.models import ProjectSizeLimitRequest
from warehouse.utils.otp import _get_totp


class TestManageProjectSettings:
    def _login(self, webtest, user):
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

    def test_request_size_limit_increase(self, webtest):
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        project = ProjectFactory.create(name="myproject")
        RoleFactory.create(user=user, project=project, role_name="Owner")
        self._login(webtest, user)

        settings_page = webtest.get(
            "/manage/project/myproject/settings/", status=HTTPStatus.OK
        )
        assert "Project details" in settings_page.text
        assert "Request an increase" in settings_page.text

        form = settings_page.forms["request-project-size-increase-form"]
        form["requested_limit"] = "20"
        form["indexes"] = "PyPI"
        form["about_project"] = "About the project"
        form["release_size"] = "Release size details"
        form["release_frequency"] = "Release frequency details"

        result_page = form.submit().follow(status=HTTPStatus.OK)

        assert "pending review" in result_page.text

        size_limit_request = (
            webtest.extra_environ["warehouse.db_session"]
            .query(ProjectSizeLimitRequest)
            .filter(ProjectSizeLimitRequest.project_id == project.id)
            .one()
        )
        assert size_limit_request.requested_limit == 20 * (1024**3)
        assert size_limit_request.indexes == "PyPI"
        assert size_limit_request.about_project == "About the project"
