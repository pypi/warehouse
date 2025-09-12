# SPDX-License-Identifier: Apache-2.0

import pytest


@pytest.mark.parametrize("path", ["/"])
def test_basic_views_dont_vary(webtest, path):
    resp = webtest.get(path)
    assert resp.headers["Vary"] in [
        "Accept-Encoding, PyPI-Locale",
        "PyPI-Locale, Accept-Encoding",
    ]
