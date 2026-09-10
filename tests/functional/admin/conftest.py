# SPDX-License-Identifier: Apache-2.0

import datetime
import time

from http import HTTPStatus

import msgpack
import pytest

from pyramid.interfaces import ISessionFactory

from tests.common.constants import REMOTE_ADDR
from tests.common.db import Session
from tests.common.db.accounts import (
    UserFactory,
    UserUniqueLoginFactory,
    WebAuthnFactory,
)
from tests.common.db.ip_addresses import IpAddressFactory
from warehouse.accounts.models import UniqueLoginStatus
from warehouse.accounts.views import USER_ID_INSECURE_COOKIE
from warehouse.ip_addresses.models import IpAddress
from warehouse.utils.msgpack import object_encode
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
        if "totp-auth-form" in two_factor_page.forms:
            two_factor_form = two_factor_page.forms["totp-auth-form"]
            two_factor_form["totp_value"] = (
                _get_totp(user.totp_secret).generate(time.time()).decode()
            )
            two_factor_form.submit().follow(status=HTTPStatus.OK)
        else:
            app = webtest.app
            while not hasattr(app, "registry"):
                if hasattr(app, "app"):
                    app = app.app
                elif hasattr(app, "application"):
                    app = app.application
                else:
                    break
            session_factory = app.registry.queryUtility(ISessionFactory)
            cookie = webtest.cookies.get("session_id")
            session_id = session_factory.signer.unsign(
                cookie, max_age=session_factory.max_age
            ).decode("utf8")
            key = session_factory._redis_key(session_id)
            bdata = session_factory.redis.get(key)
            data = msgpack.unpackb(bdata, raw=False, use_list=True) if bdata else {}
            data["auth.userid"] = str(user.id)
            csrf = session_factory.signer.sign(b"csrf").decode("utf8")
            data.setdefault("_csrf_token", csrf)
            session_factory.redis.setex(
                key,
                session_factory.max_age,
                msgpack.packb(data, default=object_encode, use_bin_type=True),
            )
            webtest.set_cookie(USER_ID_INSECURE_COOKIE, str(user.id))
            user.last_login = datetime.datetime.now(datetime.UTC)
            Session.flush()
        return user

    return _login


# Every flag that grants some admin role. Naming one picks the role outright,
# so a test asserting that a moderator is turned away cannot accidentally get a
# superuser as well and pass without exercising anything.
_ADMIN_ROLES = frozenset(
    {"is_superuser", "is_support", "is_moderator", "is_psf_staff", "is_observer"}
)


@pytest.fixture
def login_admin(login_user):
    """Create an admin user and log it in, returning the user.

    Defaults to a superuser; naming any role flag replaces that default, e.g.
    ``login_admin(is_moderator=True)`` logs in a moderator and nothing more.
    """

    def _login(**kwargs):
        roles = {} if _ADMIN_ROLES & kwargs.keys() else {"is_superuser": True}
        user = UserFactory.create(
            **{
                **roles,
                "with_verified_primary_email": True,
                "clear_pwd": "password",
                **kwargs,
            }
        )
        WebAuthnFactory.create(user=user)
        return login_user(user)

    return _login
