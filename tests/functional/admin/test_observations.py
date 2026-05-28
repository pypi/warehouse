# SPDX-License-Identifier: Apache-2.0
from http import HTTPStatus

from tests.common.db.accounts import UserFactory


class TestObservationsInsights:
    def test_insights_renders_info_boxes_via_component(self, webtest, login_user):
        admin = UserFactory.create(
            is_superuser=True,
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )

        login_user(admin)

        resp = webtest.get("/admin/observations/insights/", status=HTTPStatus.OK)

        # The corroboration stat tiles come from the info_box component; with an
        # empty DB they render zero counts.
        assert "info-box-icon bg-info" in resp.text
        assert "Total Reports" in resp.text
        assert "Corroborated Reports" in resp.text
        assert "packages with 2+ observers" in resp.text
