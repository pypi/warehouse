# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from tests.common.db.packaging import ProjectFactory


class TestProjectList:
    def test_renders_tabulator_mount_and_dashboard(self, webtest, login_admin):
        login_admin()

        page = webtest.get("/admin/projects/", status=HTTPStatus.OK)

        table = page.html.find(id="projects-table")
        assert table is not None
        assert table["data-url"] == "/admin/projects/"
        assert page.html.find(id="projectCreationsChart") is not None

    def test_json_endpoint_returns_tabulator_payload(self, webtest, login_admin):
        login_admin()
        project = ProjectFactory.create(name="struct-sdk")

        response = webtest.get(
            "/admin/projects/?filter[0][field]=name&filter[0][value]=struct",
            headers={"Accept": "application/json"},
            status=HTTPStatus.OK,
        )

        assert set(response.json.keys()) == {
            "last_page",
            "total",
            "total_estimate",
            "data",
        }
        assert [row["name"] for row in response.json["data"]] == [project.name]
