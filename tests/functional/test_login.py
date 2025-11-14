# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

from tests.common.db.accounts import UserFactory
from warehouse.accounts.models import UniqueLoginStatus, UserUniqueLogin
from warehouse.utils.otp import _get_totp


def test_unrecognized_login_with_totp(webtest):
    """
    Tests that a user with TOTP logging in from an unrecognized IP address
    is required to confirm their email address.
    """

    # Arrange: Create a user with a verified email and TOTP enabled
    user = UserFactory.create(
        with_verified_primary_email=True,
        clear_pwd="password",
    )

    # Act 1: Go to the login page
    login_page = webtest.get("/account/login/")
    assert login_page.status_code == HTTPStatus.OK

    # Fill out the login form and submit it
    login_form = login_page.forms["login-form"]
    login_form["username"] = user.username
    login_form["password"] = "password"
    resp = login_form.submit()

    # We should be redirected to the two-factor authentication page
    assert resp.status_code == HTTPStatus.SEE_OTHER
    assert resp.headers["Location"].startswith("http://localhost/account/two-factor/")
    two_factor_page = resp.follow()
    assert "Two-factor authentication" in two_factor_page

    # This is the first time we're logging in from this IP, so we should
    # be redirected to the "unrecognized login" page after submitting the
    # TOTP code.
    two_factor_form = two_factor_page.forms["totp-auth-form"]
    two_factor_form["totp_value"] = (
        _get_totp(user.totp_secret).generate(time.time()).decode()
    )
    resp = two_factor_form.submit()

    assert resp.status_code == HTTPStatus.SEE_OTHER
    assert resp.headers["Location"].endswith("/account/confirm-login/")
    unrecognized_page = resp.follow()
    assert "Unrecognized device" in unrecognized_page

    # This is a hack because the functional test doesn't have another way to
    # determine the magic link that was sent in the email. Instead, find the
    # UserUniqueLogin that was created for this user and manually confirm it
    db_session = webtest.extra_environ["warehouse.db_session"]
    unique_login = (
        db_session.query(UserUniqueLogin).filter(UserUniqueLogin.user == user).one()
    )
    assert unique_login.status == UniqueLoginStatus.PENDING
    unique_login.status = UniqueLoginStatus.CONFIRMED
    db_session.commit()

    # Act 2: Try to log in again
    login_page = webtest.get("/account/login/")
    login_form = login_page.forms["login-form"]
    login_form["username"] = user.username
    login_form["password"] = "password"
    resp = login_form.submit()

    # We should be redirected to the two-factor authentication page
    assert resp.status_code == HTTPStatus.SEE_OTHER
    assert resp.headers["Location"].startswith("http://localhost/account/two-factor/")
    two_factor_page = resp.follow()
    assert "Two-factor authentication" in two_factor_page

    # Fill out the TOTP form and submit it
    two_factor_form = two_factor_page.forms["totp-auth-form"]
    two_factor_form["totp_value"] = (
        _get_totp(user.totp_secret).generate(time.time()).decode()
    )

    # We should be able to successfully log in
    logged_in = two_factor_form.submit().follow(status=HTTPStatus.OK)
    assert logged_in.html.find("title", string="Warehouse · The Python Package Index")
