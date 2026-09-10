# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from tests.common.db.observations import ObserverFactory
from tests.common.db.packaging import ProjectFactory, ProjectObservationFactory


class TestObservationsList:
    def test_renders_tabulator_mount(self, webtest, login_admin):
        login_admin()

        page = webtest.get("/admin/observations/", status=HTTPStatus.OK)

        table = page.html.find(id="observations-table")
        assert table is not None
        assert table["data-url"] == "/admin/observations/"
        assert page.html.find(id="observations-kind-filter") is not None

    def test_json_endpoint_returns_tabulator_payload(self, webtest, login_admin):
        login_admin()

        observer = ObserverFactory.create()
        project = ProjectFactory.create()
        ProjectObservationFactory.create(
            kind="is_malware", observer=observer, related=project
        )

        response = webtest.get(
            "/admin/observations/",
            headers={"Accept": "application/json"},
            status=HTTPStatus.OK,
        )

        assert set(response.json.keys()) == {
            "last_page",
            "total",
            "total_estimate",
            "data",
        }
        assert len(response.json["data"]) == 1
