# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

from tests.common.constants import REMOTE_ADDR
from tests.common.db.accounts import UserFactory, UserUniqueLoginFactory
from tests.common.db.ip_addresses import IpAddressFactory
from warehouse.accounts.models import UniqueLoginStatus
from warehouse.utils.otp import _get_totp


class TestUserExport:
    def _login(self, webtest, user):
        """Log in a 2FA-enabled user with a pre-confirmed IP."""
        ip_address = IpAddressFactory.create(ip_address=REMOTE_ADDR)
        UserUniqueLoginFactory.create(
            user=user, ip_address=ip_address, status=UniqueLoginStatus.CONFIRMED
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

    def test_admin_sees_button_and_downloads(self, webtest):
        """An admin sees the export button and downloads the document."""
        admin = UserFactory.create(
            is_superuser=True,
            with_verified_primary_email=True,
            clear_pwd="password",
        )
        self._login(webtest, admin)
        target = UserFactory.create()

        detail = webtest.get(f"/admin/users/{target.username}/", status=HTTPStatus.OK)
        assert "User account export (JSON)" in detail.text

        export = webtest.get(
            f"/admin/users/{target.username}/export/", status=HTTPStatus.OK
        )
        assert export.content_type == "application/json"
        assert export.json["user"]["username"] == target.username

    def test_moderator_sees_no_button_and_is_denied(self, webtest):
        """A moderator neither sees the button nor can hit the route."""
        moderator = UserFactory.create(
            is_moderator=True,
            with_verified_primary_email=True,
            clear_pwd="password",
        )
        self._login(webtest, moderator)
        target = UserFactory.create()

        detail = webtest.get(f"/admin/users/{target.username}/", status=HTTPStatus.OK)
        assert "User account export (JSON)" not in detail.text

        webtest.get(
            f"/admin/users/{target.username}/export/",
            status=HTTPStatus.FORBIDDEN,
        )
