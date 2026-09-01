# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

import pytest

from tests.common.db import Session
from tests.common.db.accounts import UserFactory
from warehouse.macaroons import caveats
from warehouse.macaroons.services import DatabaseMacaroonService


@pytest.fixture
def token():
    """A real token and the macaroon behind it, as account settings mints them."""
    owner = UserFactory.create()
    return DatabaseMacaroonService(Session).create_macaroon(
        location="pypi.org",
        description="a token to look up",
        scopes=[caveats.RequestUser(user_id=str(owner.id))],
        user_id=owner.id,
    )


def _decode(webtest, raw_token):
    page = webtest.get("/admin/token/decode", status=HTTPStatus.OK)
    form = page.forms["decode-token"]
    form["token"] = raw_token
    return form.submit(status=HTTPStatus.OK)


class TestDecodeToken:
    def test_admin_sees_a_whole_token(self, webtest, login_admin, token):
        """A whole token links to the macaroon it names."""
        login_admin()
        raw_token, macaroon = token

        result = _decode(webtest, raw_token)

        assert f"/admin/macaroons/{macaroon.id}" in result.text
        assert "truncated or otherwise malformed" not in result.text

    def test_admin_sees_the_fields_a_truncated_token_holds(
        self, webtest, login_admin, token
    ):
        """A token cut a few bytes into its first caveat still names its row."""
        login_admin()
        raw_token, macaroon = token

        result = _decode(webtest, raw_token[:80])

        assert "truncated or otherwise malformed" in result.text
        assert "pypi.org" in result.text
        assert f"/admin/macaroons/{macaroon.id}" in result.text
        # The caveat's own quote character comes back HTML escaped.
        assert "[3,&#34; (truncated, 42 bytes declared)" in result.text
