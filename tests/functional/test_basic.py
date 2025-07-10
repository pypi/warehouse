# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

import pytest
import webtest


@pytest.mark.parametrize(
    ("domain", "indexable"), [("pypi.org", True), ("test.pypi.org", False)]
)
def test_robots_txt(app_config, domain, indexable):
    app_config.add_settings({"warehouse.domain": domain, "enforce_https": False})
    testapp = webtest.TestApp(app_config.make_wsgi_app())
    resp = testapp.get("/robots.txt")
    assert resp.status_code == HTTPStatus.OK
    assert resp.content_type == "text/plain"
    body = resp.body.decode(resp.charset)
    if indexable:
        assert body == (
            "Sitemap: http://localhost/sitemap.xml\n\n"
            "User-agent: *\n"
            "Disallow: /simple/\n"
            "Disallow: /packages/\n"
            "Disallow: /_includes/authed/\n"
            "Disallow: /pypi/*/json\n"
            "Disallow: /pypi/*/*/json\n"
            "Disallow: /pypi*?\n"
            "Disallow: /search*\n"
            "Disallow: /_/\n"
            "Disallow: /integrity/\n"
            "Disallow: /admin/\n"
        )
    else:
        assert body == (
            "Sitemap: http://localhost/sitemap.xml\n\n"
            "User-agent: *\n"
            "Disallow: /\n"
        )


def test_non_existent_route_404(webtest):
    resp = webtest.get("/asdadadasdasd/", status=HTTPStatus.NOT_FOUND)
    assert resp.status_code == HTTPStatus.NOT_FOUND
