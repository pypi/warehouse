# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

from warehouse.accounts.models import UniqueLoginStatus
from warehouse.utils.otp import _get_totp

from ...common.constants import REMOTE_ADDR
from ...common.db.accounts import UserFactory, UserUniqueLoginFactory
from ...common.db.ip_addresses import IpAddressFactory
from ...common.db.macaroons import MacaroonFactory


class TestManageAccountTokens:
    def _login_user(self, webtest, user):
        """Log a user in, submitting TOTP only when the user has 2FA."""
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

    def test_lists_tokens(self, webtest):
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        macaroon = MacaroonFactory.create(
            user_id=user.id,
            description="my token",
            permissions_caveat={"permissions": "user"},
        )

        self._login_user(webtest, user)

        tokens_page = webtest.get("/manage/account/tokens/", status=HTTPStatus.OK)

        assert "API tokens" in tokens_page.text
        assert macaroon.description in tokens_page.text
        assert str(macaroon.id) in tokens_page.text
        assert "/manage/account/token/" in tokens_page.text

    def test_lists_tokens_when_empty(self, webtest):
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )

        self._login_user(webtest, user)

        tokens_page = webtest.get("/manage/account/tokens/", status=HTTPStatus.OK)

        assert "You have not created any API tokens yet." in tokens_page.text

    def test_accessible_without_two_factor(self, webtest):
        """The page must stay reachable for users who have not enabled 2FA."""
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
            totp_secret=None,
        )

        self._login_user(webtest, user)

        tokens_page = webtest.get("/manage/account/tokens/", status=HTTPStatus.OK)

        assert "API tokens" in tokens_page.text

    def test_account_page_links_to_tokens_page(self, webtest):
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )

        self._login_user(webtest, user)

        account_page = webtest.get("/manage/account/", status=HTTPStatus.OK)

        assert account_page.html.find("a", href="/manage/account/tokens/") is not None
