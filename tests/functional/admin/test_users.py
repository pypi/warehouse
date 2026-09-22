# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from tests.common.db.accounts import UserFactory


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
