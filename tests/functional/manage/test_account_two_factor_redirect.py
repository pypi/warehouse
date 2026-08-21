# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

from warehouse.accounts.models import UniqueLoginStatus
from warehouse.utils.otp import _get_totp

from ...common.constants import REMOTE_ADDR
from ...common.db.accounts import UserFactory, UserUniqueLoginFactory
from ...common.db.ip_addresses import IpAddressFactory


class TestTwoFactorRouteRedirect:
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
            assert response.status_code == HTTPStatus.SEE_OTHER
            return

        two_factor_page = response.follow(status=HTTPStatus.OK)
        two_factor_form = two_factor_page.forms["totp-auth-form"]
        two_factor_form["totp_value"] = (
            _get_totp(user.totp_secret).generate(time.time()).decode()
        )
        two_factor_form.submit().follow(status=HTTPStatus.OK)

    def test_two_factor_route_redirects_preserving_query_string(self, webtest):
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )

        self._login_user(webtest, user)

        response = webtest.get(
            "/manage/account/two-factor/?next=%2Fmanage%2Fprojects%2F",
            status=HTTPStatus.FOUND,
        )

        assert response.headers["Location"] == (
            "http://localhost/manage/account/security/"
            "?next=%2Fmanage%2Fprojects%2F#two-factor"
        )
