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


class TestObservationsInsights:
    def test_insights_renders_info_boxes_via_component(self, webtest, login_admin):
        login_admin(with_terms_of_service_agreement=True)

        resp = webtest.get("/admin/observations/insights/", status=HTTPStatus.OK)

        # The corroboration stat tiles come from the info_box component; with an
        # empty DB they render zero counts.
        assert "info-box-icon bg-info" in resp.text
        assert "Total Reports" in resp.text
        assert "Corroborated Reports" in resp.text
        assert "packages with 2+ observers" in resp.text
        assert "N/A" in resp.text  # no reports, so no corroboration rate

    def test_insights_renders_corroboration_rate_when_reports_exist(
        self, webtest, login_admin, make_malware_report
    ):
        """With a report present the rate tile renders a percentage, not "N/A"."""
        login_admin(with_terms_of_service_agreement=True)
        make_malware_report()

        resp = webtest.get("/admin/observations/insights/", status=HTTPStatus.OK)

        assert "Corroboration Rate" in resp.text
        assert "0.0%" in resp.text  # one report, no package corroborated


class TestObserverReputation:
    def test_reputation_renders_stat_cards_via_component(self, webtest, login_admin):
        login_admin(with_terms_of_service_agreement=True)

        resp = webtest.get("/admin/observers/reputation/", status=HTTPStatus.OK)

        # The summary tiles come from the stat_card component; with an empty DB
        # the accuracy rate has no data and renders as N/A.
        assert "small-box bg-info" in resp.text
        assert "Total Malware Reports" in resp.text
        assert "Overall Accuracy Rate" in resp.text
        assert "N/A" in resp.text
        assert "Active Observers" in resp.text

    def test_reputation_renders_accuracy_rate_when_resolved(
        self, webtest, login_admin, make_malware_report
    ):
        """A resolved report takes the percentage branch instead of the "N/A" one."""
        login_admin(with_terms_of_service_agreement=True)
        make_malware_report({"1": {"action": "remove_malware"}})

        resp = webtest.get("/admin/observers/reputation/", status=HTTPStatus.OK)

        assert "Overall Accuracy Rate" in resp.text
        assert "100.0%" in resp.text
