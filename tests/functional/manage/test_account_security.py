# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

from warehouse.accounts.models import UniqueLoginStatus
from warehouse.utils.otp import _get_totp

from ...common.constants import REMOTE_ADDR
from ...common.db.accounts import UserFactory, UserUniqueLoginFactory
from ...common.db.ip_addresses import IpAddressFactory


class TestAccountSecurity:
    def _login_user(self, webtest, user):
        """Log a user in, submitting TOTP only when the user has 2FA."""
        UserUniqueLoginFactory.create(
            user=user,
            ip_address=IpAddressFactory.create(ip_address=REMOTE_ADDR),
            status=UniqueLoginStatus.CONFIRMED,
        )

        login_page = webtest.get("/account/login/", status=HTTPStatus.OK)
        login_form = login_page.forms["login-form"]
        login_form["username"] = user.username
        login_form["password"] = "password"
        response = login_form.submit()

        if user.totp_secret is None:
            # Without 2FA the login lands on the "enable 2FA" nudge instead of
            # a second authentication step.
            assert response.status_code == HTTPStatus.SEE_OTHER
            return

        two_factor_page = response.follow(status=HTTPStatus.OK)
        two_factor_form = two_factor_page.forms["totp-auth-form"]
        two_factor_form["totp_value"] = (
            _get_totp(user.totp_secret).generate(time.time()).decode()
        )
        two_factor_form.submit().follow(status=HTTPStatus.OK)

    def test_security_page(self, webtest):
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )

        self._login_user(webtest, user)

        security_page = webtest.get("/manage/account/security/", status=HTTPStatus.OK)

        assert "Change password" in security_page.text
        assert "Two factor authentication (2FA)" in security_page.text
        assert security_page.forms["change-password-form"] is not None

    def test_security_page_without_two_factor(self, webtest):
        """The page must stay reachable for users who have not enabled 2FA."""
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
            totp_secret=None,
        )

        self._login_user(webtest, user)

        assert not user.has_two_factor

        security_page = webtest.get("/manage/account/security/", status=HTTPStatus.OK)

        assert "Two factor authentication (2FA)" in security_page.text

    def test_change_password(self, webtest):
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )

        self._login_user(webtest, user)

        security_page = webtest.get("/manage/account/security/", status=HTTPStatus.OK)
        form = security_page.forms["change-password-form"]
        form["password"] = "password"
        form["new_password"] = "an3w-P455w0rd!"
        form["password_confirm"] = "an3w-P455w0rd!"

        form.submit().follow(status=HTTPStatus.OK)

        flash = webtest.get("/_includes/unauthed/flash-messages/", status=HTTPStatus.OK)
        message = flash.html.find("span", {"class": "notification-bar__message"})
        assert message.text == "Password updated"

    def test_account_page_links_to_security_page(self, webtest):
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )

        self._login_user(webtest, user)

        account_page = webtest.get("/manage/account/", status=HTTPStatus.OK)

        # The account navigation exposes Security plus its sub-items
        assert account_page.html.find("a", href="/manage/account/security/") is not None
        assert account_page.html.find("a", href="/manage/account/tokens/") is not None
        assert (
            account_page.html.find("a", href="/manage/account/security-history/")
            is not None
        )
