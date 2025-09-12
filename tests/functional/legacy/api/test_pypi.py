# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus


def test_doap(webtest):
    resp = webtest.get(
        "/pypi?:action=doap&name=foo&version=1.0", status=HTTPStatus.GONE
    )
    assert resp.status == "410 DOAP is no longer supported."
