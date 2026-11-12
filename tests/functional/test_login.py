# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

from tests.common.db.accounts import UserFactory
from warehouse.accounts import services
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
    assert "Please confirm this login" in unrecognized_page

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


def test_unrecognized_login_remember_device_via_email_link(webtest, mocker):
    """
    Tests that "remember this device", ticked on a TOTP login from an
    unrecognized IP address, takes effect once the emailed confirmation link
    is followed, so the next login skips two-factor authentication.
    """
    user = UserFactory.create(
        with_verified_primary_email=True,
        clear_pwd="password",
    )
    send_email = mocker.patch.object(
        services,
        "send_unrecognized_login_email",
        wraps=services.send_unrecognized_login_email,
    )

    login_page = webtest.get("/account/login/")
    login_form = login_page.forms["login-form"]
    login_form["username"] = user.username
    login_form["password"] = "password"
    two_factor_page = login_form.submit().follow(status=HTTPStatus.OK)

    two_factor_form = two_factor_page.forms["totp-auth-form"]
    two_factor_form["totp_value"] = (
        _get_totp(user.totp_secret).generate(time.time()).decode()
    )
    two_factor_form["remember_device"] = True
    resp = two_factor_form.submit()

    # Unrecognized device: sent to confirm, and nothing is remembered yet
    assert resp.status_code == HTTPStatus.SEE_OTHER
    assert resp.headers["Location"].endswith("/account/confirm-login/")
    assert "remember_device" not in webtest.cookies

    # Follow the link from the email
    token = send_email.call_args.kwargs["token"]
    resp = webtest.get("/account/confirm-login/", params={"token": token})
    assert resp.status_code == HTTPStatus.SEE_OTHER
    assert resp.headers["Location"].endswith("/manage/projects/")
    assert "remember_device" in webtest.cookies

    # Drop the session but keep the remembered-device cookie, then log in again
    # from a new IP address
    for cookie in list(webtest.cookiejar):
        if cookie.name == "session_id":
            webtest.cookiejar.clear(cookie.domain, cookie.path, cookie.name)
    login_page = webtest.get("/account/login/")
    login_form = login_page.forms["login-form"]
    login_form["username"] = user.username
    login_form["password"] = "password"
    resp = login_form.submit(extra_environ={"REMOTE_ADDR": "203.0.113.2"})

    # The remembered device skips two-factor authentication, but does not
    # confirm the new IP address since the device was remembered via TOTP
    assert resp.status_code == HTTPStatus.SEE_OTHER
    assert resp.headers["Location"].endswith("/manage/projects/")
    db_session = webtest.extra_environ["warehouse.db_session"]
    unique_logins = (
        db_session.query(UserUniqueLogin).filter(UserUniqueLogin.user == user).all()
    )
    assert len(unique_logins) == 1


def test_frozen_user_remember_device_via_email_link(webtest, mocker):
    """
    Tests that a frozen user who ticks "remember this device" and follows the
    emailed confirmation link is redirected rather than hitting a server error,
    and is still not logged in afterwards.
    """
    user = UserFactory.create(
        with_verified_primary_email=True,
        clear_pwd="password",
        is_frozen=True,
    )
    send_email = mocker.patch.object(
        services,
        "send_unrecognized_login_email",
        wraps=services.send_unrecognized_login_email,
    )

    login_page = webtest.get("/account/login/")
    login_form = login_page.forms["login-form"]
    login_form["username"] = user.username
    login_form["password"] = "password"
    two_factor_page = login_form.submit().follow(status=HTTPStatus.OK)

    two_factor_form = two_factor_page.forms["totp-auth-form"]
    two_factor_form["totp_value"] = (
        _get_totp(user.totp_secret).generate(time.time()).decode()
    )
    two_factor_form["remember_device"] = True
    resp = two_factor_form.submit()
    assert resp.headers["Location"].endswith("/account/confirm-login/")

    # Follow the link from the email
    token = send_email.call_args.kwargs["token"]
    resp = webtest.get("/account/confirm-login/", params={"token": token})
    assert resp.status_code == HTTPStatus.SEE_OTHER

    # The frozen account is not logged in
    resp = webtest.get("/manage/projects/")
    assert resp.status_code == HTTPStatus.SEE_OTHER
    assert "/account/login/" in resp.headers["Location"]
