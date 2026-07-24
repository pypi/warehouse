# SPDX-License-Identifier: Apache-2.0
from http import HTTPStatus

from tests.common.db.accounts import UserFactory


class TestAdminDashboard:
    def test_dashboard_renders_stat_cards_via_component(self, webtest, login_user):
        admin = UserFactory.create(
            is_superuser=True,
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )

        login_user(admin)

        resp = webtest.get("/admin/", status=HTTPStatus.OK)

        # The Organizations "Approved" card (always rendered) and its footer link
        # now come from the stat_card component.
        assert "small-box bg-gradient-info" in resp.text
        assert "0 Approved" in resp.text  # empty DB → zero approved orgs
        assert "small-box-footer" in resp.text
        assert "View All Reviewable" in resp.text
