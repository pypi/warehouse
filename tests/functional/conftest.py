# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

import pytest

from tests.common.constants import REMOTE_ADDR
from tests.common.db import Session
from tests.common.db.accounts import UserUniqueLoginFactory
from tests.common.db.ip_addresses import IpAddressFactory
from warehouse.accounts.models import UniqueLoginStatus
from warehouse.ip_addresses.models import IpAddress
from warehouse.utils.otp import _get_totp


@pytest.fixture
def login_user(webtest):
    """Log a 2FA-enabled user in, from an already-confirmed IP address."""

    def _login(user):
        # `ip_address` is unique and any request already served in this test
        # will have inserted the row, since every request upserts it in
        # warehouse.utils.wsgi._ip_address. Reuse it rather than collide.
        ip_address = Session.query(IpAddress).filter_by(
            ip_address=REMOTE_ADDR
        ).one_or_none() or IpAddressFactory.create(ip_address=REMOTE_ADDR)
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
        return user

    return _login
