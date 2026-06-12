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


class TestObserverReputation:
    def test_reputation_renders_stat_cards_via_component(self, webtest, login_user):
        admin = UserFactory.create(
            is_superuser=True,
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )

        login_user(admin)

        resp = webtest.get("/admin/observers/reputation/", status=HTTPStatus.OK)

        # The summary tiles come from the stat_card component; with an empty DB
        # the accuracy rate has no data and renders as N/A.
        assert "small-box bg-info" in resp.text
        assert "Total Malware Reports" in resp.text
        assert "Overall Accuracy Rate" in resp.text
        assert "N/A" in resp.text
        assert "Active Observers" in resp.text
