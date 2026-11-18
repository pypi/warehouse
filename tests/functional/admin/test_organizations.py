# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from tests.common.db.organizations import OrganizationFactory


class TestOrganizationList:
    def test_renders_tabulator_mount(self, webtest, login_admin):
        login_admin()

        page = webtest.get("/admin/organizations/", status=HTTPStatus.OK)

        table = page.html.find(id="organizations-table")
        assert table is not None
        assert table["data-url"] == "/admin/organizations/"

    def test_json_endpoint_returns_tabulator_payload(self, webtest, login_admin):
        login_admin()
        organization = OrganizationFactory.create()

        response = webtest.get(
            "/admin/organizations/",
            headers={"Accept": "application/json"},
            status=HTTPStatus.OK,
        )

        assert set(response.json.keys()) == {
            "last_page",
            "total",
            "total_estimate",
            "data",
        }
        assert [row["name"] for row in response.json["data"]] == [organization.name]
