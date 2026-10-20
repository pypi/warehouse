# SPDX-License-Identifier: Apache-2.0
from http import HTTPStatus


class TestAdminDashboard:
    def test_dashboard_renders_stat_cards(self, webtest, login_admin):
        login_admin(with_terms_of_service_agreement=True)

        resp = webtest.get("/admin/", status=HTTPStatus.OK)

        # Empty DB, so zero approved organizations.
        approved = resp.html.find("h3", string="0 Approved").find_parent(
            "div", class_="small-box"
        )
        assert "bg-gradient-info" in approved["class"]
        assert approved.find("i", class_="fa-people-group") is not None
        footer = approved.find("a", class_="small-box-footer")
        assert footer["href"] == "/admin/organizations/"
        assert footer.get_text(strip=True) == "View All"

        with_projects = resp.html.find("h3", string="0 With Projects").find_parent(
            "div", class_="small-box"
        )
        assert with_projects.find("a", class_="small-box-footer") is None
        tooltip = with_projects.find("i", class_="info-icon")
        assert tooltip["title"] == "Organizations that have at least one project"

    def test_dashboard_renders_malware_card_when_reports_exist(
        self, webtest, login_admin, make_malware_report
    ):
        """The malware card sits behind `{% if malware_reports_count %}`.

        It is the only call site combining `description` with a footer, so with no
        open report nothing renders that prop combination.
        """
        login_admin(with_terms_of_service_agreement=True)
        make_malware_report()

        resp = webtest.get("/admin/", status=HTTPStatus.OK)

        card = resp.html.find("h3", string="1").find_parent("div", class_="small-box")
        assert "bg-gradient-warning" in card["class"]
        assert card.find("p").get_text(strip=True) == "Open Malware Reports"
        footer = card.find("a", class_="small-box-footer")
        assert footer["href"] == "/admin/malware_reports/"
        assert footer.get_text(strip=True) == "More info"
