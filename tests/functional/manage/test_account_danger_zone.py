# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from warehouse.accounts.models import UniqueLoginStatus

from ...common.constants import REMOTE_ADDR
from ...common.db.accounts import UserFactory, UserUniqueLoginFactory
from ...common.db.ip_addresses import IpAddressFactory
from ...common.db.packaging import ProjectFactory, RoleFactory


class TestAccountDangerZone:
    def _login(self, webtest, user):
        UserUniqueLoginFactory.create(
            user=user,
            ip_address=IpAddressFactory.create(ip_address=REMOTE_ADDR),
            status=UniqueLoginStatus.CONFIRMED,
        )
        login_page = webtest.get("/account/login/", status=HTTPStatus.OK)
        login_form = login_page.forms["login-form"]
        login_form["username"] = user.username
        login_form["password"] = "password"
        login_form.submit(status=HTTPStatus.SEE_OTHER)

    def test_account_page_links_to_danger_zone(self, webtest):
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
            totp_secret=None,
        )
        self._login(webtest, user)

        account_page = webtest.get("/manage/account/", status=HTTPStatus.OK)

        assert (
            account_page.html.find("a", href="/manage/account/danger-zone/") is not None
        )
        section = account_page.html.find("section", id="delete-account")
        assert section.find("h2").text.strip() == "Danger zone"

    def test_danger_zone_renders_deletable_account(self, webtest):
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
            totp_secret=None,
        )
        self._login(webtest, user)

        page = webtest.get("/manage/account/danger-zone/", status=HTTPStatus.OK)

        callout = page.html.find("div", class_="callout-block")
        assert "callout-block--danger" in callout["class"]
        assert "Delete your PyPI account" in callout.text

    def test_danger_zone_renders_blocked_account(self, webtest):
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
            totp_secret=None,
        )
        RoleFactory.create(
            user=user, project=ProjectFactory.create(), role_name="Owner"
        )
        self._login(webtest, user)

        page = webtest.get("/manage/account/danger-zone/", status=HTTPStatus.OK)

        callout = page.html.find("div", class_="callout-block")
        # The block stays danger-styled even when deletion is currently blocked.
        assert "callout-block--danger" in callout["class"]
        assert "Cannot delete account" in callout.text
        assert "Delete your PyPI account" not in callout.text
