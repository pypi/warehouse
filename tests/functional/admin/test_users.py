# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from tests.common.db.accounts import UserFactory
from tests.common.db.macaroons import MacaroonFactory


class TestUserList:
    def test_renders_tabulator_mount(self, webtest, login_admin):
        login_admin()

        page = webtest.get("/admin/users/", status=HTTPStatus.OK)

        table = page.html.find(id="users-table")
        assert table is not None
        assert table["data-url"] == "/admin/users/"

    def test_json_endpoint_returns_tabulator_payload(self, webtest, login_admin):
        admin = login_admin()

        response = webtest.get(
            "/admin/users/",
            headers={"Accept": "application/json"},
            status=HTTPStatus.OK,
        )

        assert set(response.json.keys()) == {
            "last_page",
            "total",
            "total_estimate",
            "data",
        }
        assert [row["username"] for row in response.json["data"]] == [admin.username]


class TestUserExport:
    def test_admin_sees_button_and_downloads(self, webtest, login_admin):
        """An admin sees the export button and downloads the document."""
        login_admin()
        target = UserFactory.create()

        detail = webtest.get(f"/admin/users/{target.username}/", status=HTTPStatus.OK)
        assert "User account export (JSON)" in detail.text

        export = webtest.get(
            f"/admin/users/{target.username}/export/", status=HTTPStatus.OK
        )
        assert export.content_type == "application/json"
        assert export.json["user"]["username"] == target.username

    def test_moderator_sees_no_button_and_is_denied(self, webtest, login_admin):
        """A moderator neither sees the button nor can hit the route."""
        login_admin(is_moderator=True)
        target = UserFactory.create()

        detail = webtest.get(f"/admin/users/{target.username}/", status=HTTPStatus.OK)
        assert "User account export (JSON)" not in detail.text

        webtest.get(
            f"/admin/users/{target.username}/export/",
            status=HTTPStatus.FORBIDDEN,
        )


class TestUserDetailTables:
    def test_account_activity_keeps_hidden_address_columns(self, webtest, login_admin):
        """
        The address columns render but start hidden, so the column menu is
        what an admin uses to reach them.
        """
        admin = login_admin()

        page = webtest.get(f"/admin/users/{admin.username}/", status=HTTPStatus.OK)

        table = page.html.find(id="account-activity")
        assert table.has_attr("data-tabulator-column-menu")
        headers = {
            th.get_text(strip=True): th for th in table.find("thead").find_all("th")
        }
        assert headers["IP address"]["tabulator-visible"] == "false"
        assert headers["Hashed IP address"]["tabulator-visible"] == "false"
        # The login itself is an event, so the table is not empty.
        assert table.find("tbody").find_all("tr")

    def test_api_tokens_keeps_hidden_permissions_column(self, webtest, login_admin):
        admin = login_admin()
        MacaroonFactory.create(user_id=admin.id, description="a token")

        page = webtest.get(f"/admin/users/{admin.username}/", status=HTTPStatus.OK)

        table = page.html.find(id="api-tokens")
        assert table.has_attr("data-tabulator-column-menu")
        permissions = next(
            th
            for th in table.find("thead").find_all("th")
            if "Permissions" in th.get_text()
        )
        assert permissions["tabulator-visible"] == "false"
        assert "a token" in table.get_text()
