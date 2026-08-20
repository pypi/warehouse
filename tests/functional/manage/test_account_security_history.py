# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

from warehouse.accounts.models import UniqueLoginStatus
from warehouse.utils.otp import _get_totp

from ...common.constants import REMOTE_ADDR
from ...common.db.accounts import UserFactory, UserUniqueLoginFactory
from ...common.db.ip_addresses import IpAddressFactory


class TestAccountSecurityHistory:
    def _confirm_login_ip(self, user):
        """Pre-confirm the test IP so login skips device confirmation."""
        UserUniqueLoginFactory.create(
            user=user,
            ip_address=IpAddressFactory.create(ip_address=REMOTE_ADDR),
            status=UniqueLoginStatus.CONFIRMED,
        )

    def _submit_login(self, webtest, user, status=HTTPStatus.SEE_OTHER):
        login_page = webtest.get("/account/login/", status=HTTPStatus.OK)
        login_form = login_page.forms["login-form"]
        login_form["username"] = user.username
        login_form["password"] = "password"
        return login_form.submit(status=status)

    def test_security_history_page(self, webtest):
        """A user with 2FA can load their security history page."""
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        self._confirm_login_ip(user)

        two_factor_page = self._submit_login(webtest, user).follow(status=HTTPStatus.OK)
        two_factor_form = two_factor_page.forms["totp-auth-form"]
        two_factor_form["totp_value"] = (
            _get_totp(user.totp_secret).generate(time.time()).decode()
        )
        two_factor_form.submit().follow(status=HTTPStatus.OK)

        history_page = webtest.get(
            "/manage/account/security-history/", status=HTTPStatus.OK
        )

        assert "Security history" in history_page.text
        # The login we just performed is recorded and rendered
        assert "Logged in" in history_page.text

        # The account settings page links here instead of rendering the table
        account_page = webtest.get("/manage/account/", status=HTTPStatus.OK)
        assert (
            account_page.html.find(
                "a", href="/manage/account/security-history/", string=True
            )
            is not None
        )

    def test_security_history_page_without_two_factor(self, webtest):
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
            totp_secret=None,
        )
        self._confirm_login_ip(user)

        self._submit_login(webtest, user, status=HTTPStatus.SEE_OTHER)

        assert not user.has_two_factor

        history_page = webtest.get(
            "/manage/account/security-history/", status=HTTPStatus.OK
        )

        assert "Security history" in history_page.text
        assert "Logged in" in history_page.text
