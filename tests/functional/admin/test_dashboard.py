# SPDX-License-Identifier: Apache-2.0
from http import HTTPStatus


class TestAdminDashboard:
    def test_dashboard_renders_stat_cards_via_component(self, webtest, login_admin):
        login_admin(with_terms_of_service_agreement=True)

        resp = webtest.get("/admin/", status=HTTPStatus.OK)

        # The Organizations "Approved" card (always rendered) and its footer link
        # now come from the stat_card component.
        assert "small-box bg-gradient-info" in resp.text
        assert "0 Approved" in resp.text  # empty DB, zero approved orgs
        assert "small-box-footer" in resp.text
        assert "View All Reviewable" in resp.text

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

        assert "small-box bg-gradient-warning" in resp.text
        assert "Open Malware Reports" in resp.text
        assert "More info" in resp.text
