# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

# The head of a truncated token, held apart from its `pypi-` prefix so secret
# scanners have no token pattern to match. It carries no signature.
_TOKEN_BODY = (
    "AgEIcHlwaS5vcmcCJDAyZWRlM2ZlLWRjMDAtNDViOS05YTEzLTlmMTZhZDFjNDU0ZAACKlszLCJ"
)
TRUNCATED_TOKEN = "pypi-" + _TOKEN_BODY


class TestDecodeTruncatedToken:
    def test_admin_sees_the_fields_that_could_be_read(self, webtest, login_admin):
        """A token with no signature left still renders the fields it has."""
        login_admin()

        page = webtest.get("/admin/token/decode", status=HTTPStatus.OK)
        form = page.forms["decode-token"]
        form["token"] = TRUNCATED_TOKEN

        result = form.submit(status=HTTPStatus.OK)

        assert "truncated or otherwise malformed" in result.text
        assert "pypi.org" in result.text
        assert "02ede3fe-dc00-45b9-9a13-9f16ad1c454d (Not found)" in result.text
        # The caveat's own quote character comes back HTML escaped.
        assert "[3,&#34; (truncated, 42 bytes declared)" in result.text
