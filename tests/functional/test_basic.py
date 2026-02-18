# SPDX-License-Identifier: Apache-2.0

import re
import time

from datetime import datetime, timezone
from http import HTTPStatus

import pytest
import webtest

from warehouse.accounts.models import UniqueLoginStatus
from warehouse.utils.otp import _get_totp

from ..common.constants import REMOTE_ADDR
from ..common.db.accounts import UserFactory, UserUniqueLoginFactory
from ..common.db.ip_addresses import IpAddressFactory
from ..common.db.packaging import ProjectFactory, RoleFactory


def test_funding_manifest_urls(app_config):
    testapp = webtest.TestApp(app_config.make_wsgi_app())
    resp = testapp.get("/.well-known/funding-manifest-urls")
    assert resp.status_code == HTTPStatus.OK
    assert resp.content_type == "text/plain"
    assert resp.body.decode(resp.charset) == "https://www.python.org/funding.json"


def test_security_txt(app_config):
    testapp = webtest.TestApp(app_config.make_wsgi_app())
    resp = testapp.get("/.well-known/security.txt")
    assert resp.status_code == HTTPStatus.OK
    assert resp.content_type == "text/plain"
    body = resp.body.decode(resp.charset)
    # Verify required fields
    assert "Contact: mailto:security@pypi.org" in body
    assert "Expires:" in body
    # Verify optional fields
    assert "Preferred-Languages: en" in body
    # In test environment, route_url generates localhost URLs
    assert "Canonical: http://localhost/.well-known/security.txt" in body
    assert "Policy: http://localhost/security/" in body
    # File must end with a newline
    assert body.endswith("\n")
    # Verify Expires is 1 year in the future
    expires_match = re.search(r"Expires: (\d{4})-(\d{2})-\d{2}", body)
    assert expires_match is not None
    expires_year = int(expires_match.group(1))
    expires_month = int(expires_match.group(2))
    now = datetime.now(timezone.utc)
    assert expires_year == now.year + 1
    assert expires_month == now.month


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
            "Disallow: /account/\n"
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


def test_uncheck_nightly_deletes_old_releases(webtest):
    user = UserFactory.create(
        with_verified_primary_email=True,
        with_terms_of_service_agreement=True,
        clear_pwd="password",
    )
    ip_address = IpAddressFactory.create(ip_address=REMOTE_ADDR)
    UserUniqueLoginFactory.create(
        user=user, ip_address=ip_address, status=UniqueLoginStatus.CONFIRMED
    )
    project = ProjectFactory.create(releases_expire_after_days=90)
    RoleFactory.create(user=user, project=project, role_name="Owner")

    # Login
    login_page = webtest.get("/account/login/", status=200)
    login_form = login_page.forms["login-form"]
    login_form["password"] = "password"
    login_form["username"] = user.username
    two_factor_page = login_form.submit().follow(status=HTTPStatus.OK)

    two_factor_form = two_factor_page.forms["totp-auth-form"]
    two_factor_form["totp_value"] = (
        _get_totp(user.totp_secret).generate(time.time()).decode()
    )
    logged_in = two_factor_form.submit().follow(status=HTTPStatus.OK)

    settings_page = logged_in.goto(
        f"/manage/project/{project.name}/settings/", status=200
    )

    settings_form = [
        form for form in settings_page.forms.values() if "is_nightly" in form.fields
    ][0]

    settings_form.get("is_nightly", index=1).checked = False
    response = settings_form.submit("submit", status=303)

    assert response.status_code == 303
    assert project.releases_expire_after_days is None
