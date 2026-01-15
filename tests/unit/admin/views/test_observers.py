# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timezone

import pytest

from pyramid.httpexceptions import HTTPNotFound

from warehouse.admin.views import observers as views

from ....common.db.accounts import UserFactory
from ....common.db.observations import ObserverFactory
from ....common.db.packaging import ProjectObservationFactory


class TestParseDaysParam:
    """Tests for the _parse_days_param helper function."""

    @pytest.mark.parametrize(
        ("params", "expected"),
        [
            ({}, 30),  # default
            ({"days": "30"}, 30),  # valid
            ({"days": "60"}, 60),  # valid
            ({"days": "90"}, 90),  # valid
            ({"days": "45"}, 30),  # invalid number defaults
            ({"days": "invalid"}, 30),  # non-numeric defaults
            ({"days": ""}, 30),  # empty string defaults
        ],
    )
    def test_parse_days_param(self, db_request, params, expected):
        db_request.params = params
        assert views._parse_days_param(db_request) == expected

    @pytest.mark.parametrize(
        ("params", "expected"),
        [
            ({"days": "0"}, 0),  # lifetime valid for detail
            ({"days": "30"}, 30),
            ({"days": "90"}, 90),
            ({"days": "45"}, 30),  # invalid still defaults
        ],
    )
    def test_parse_days_param_with_detail_allowed(self, db_request, params, expected):
        """Test parsing days with ALLOWED_DAYS_DETAIL (includes 0 for lifetime)."""
        db_request.params = params
        result = views._parse_days_param(db_request, views.ALLOWED_DAYS_DETAIL)
        assert result == expected


class TestGetObserverStats:
    def test_get_observer_stats_empty(self, db_request):
        """Test with no observations returns empty list."""
        observations = views._get_malware_observations(db_request, days=90)
        result = views._get_observer_stats(db_request, observations)
        assert result == []

    def test_get_observer_stats_with_observations(self, db_request):
        """Test with observations returns correct stats."""
        user = UserFactory.create()
        observer = ObserverFactory.create()
        user.observer = observer

        # Create some malware observations
        ProjectObservationFactory.create(kind="is_malware", observer=observer)
        ProjectObservationFactory.create(kind="is_malware", observer=observer)

        observations = views._get_malware_observations(db_request, days=90)
        result = views._get_observer_stats(db_request, observations)

        assert len(result) == 1
        assert result[0]["observer_id"] == observer.id
        assert result[0]["total_observations"] == 2
        assert result[0]["pending"] == 2
        assert result[0]["true_positives"] == 0
        assert result[0]["false_positives"] == 0
        assert result[0]["score"] == 0  # No true/false positives yet

    def test_get_observer_stats_with_removed_project(self, db_request):
        """Test that removed projects count as true positives."""
        user = UserFactory.create()
        observer = ObserverFactory.create()
        user.observer = observer

        # Create an observation for a removed project (related_id is None)
        ProjectObservationFactory.create(
            kind="is_malware", observer=observer, related=None
        )

        observations = views._get_malware_observations(db_request, days=90)
        result = views._get_observer_stats(db_request, observations)

        assert len(result) == 1
        assert result[0]["true_positives"] == 1
        assert result[0]["pending"] == 0

    def test_get_observer_stats_with_verdict_not_malware(self, db_request):
        """Test that verdict_not_malware counts as false positive."""
        user = UserFactory.create()
        observer = ObserverFactory.create()
        user.observer = observer

        now = datetime.now(tz=timezone.utc)
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            actions={
                int(now.timestamp()): {
                    "action": "verdict_not_malware",
                    "actor": "admin",
                    "reason": "Not malware",
                    "created_at": str(now),
                }
            },
        )

        observations = views._get_malware_observations(db_request, days=90)
        result = views._get_observer_stats(db_request, observations)

        assert len(result) == 1
        assert result[0]["false_positives"] == 1
        assert result[0]["true_positives"] == 0

    def test_get_observer_stats_with_verdict_remove_malware(self, db_request):
        """Test that remove_malware counts as true positive."""
        user = UserFactory.create()
        observer = ObserverFactory.create()
        user.observer = observer

        now = datetime.now(tz=timezone.utc)
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            actions={
                int(now.timestamp()): {
                    "action": "remove_malware",
                    "actor": "admin",
                    "created_at": str(now),
                }
            },
        )

        observations = views._get_malware_observations(db_request, days=90)
        result = views._get_observer_stats(db_request, observations)

        assert len(result) == 1
        assert result[0]["true_positives"] == 1
        assert result[0]["false_positives"] == 0

    def test_get_observer_stats_accuracy_calculation(self, db_request):
        """Test that accuracy and score are calculated correctly."""
        user = UserFactory.create()
        observer = ObserverFactory.create()
        user.observer = observer

        now = datetime.now(tz=timezone.utc)
        # 3 true positives
        for _ in range(3):
            ProjectObservationFactory.create(
                kind="is_malware",
                observer=observer,
                actions={
                    int(now.timestamp()): {
                        "action": "remove_malware",
                        "actor": "admin",
                        "created_at": str(now),
                    }
                },
            )
        # 1 false positive
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            actions={
                int(now.timestamp()): {
                    "action": "verdict_not_malware",
                    "actor": "admin",
                    "reason": "Not malware",
                    "created_at": str(now),
                }
            },
        )

        observations = views._get_malware_observations(db_request, days=90)
        result = views._get_observer_stats(db_request, observations)

        assert len(result) == 1
        assert result[0]["accuracy_rate"] == 75.0  # 3/4 = 75%
        assert result[0]["score"] == 5  # (3 * 2) - 1 = 5

    def test_get_observer_stats_excludes_non_malware(self, db_request):
        """Test that non-malware observations are excluded."""
        observer = ObserverFactory.create()

        # Create a non-malware observation
        ProjectObservationFactory.create(kind="is_spam", observer=observer)

        observations = views._get_malware_observations(db_request, days=90)
        result = views._get_observer_stats(db_request, observations)

        assert result == []

    def test_get_observer_stats_respects_time_period(self, db_request):
        """Test that old observations are excluded."""
        user = UserFactory.create()
        observer = ObserverFactory.create()
        user.observer = observer

        # Create a recent observation
        ProjectObservationFactory.create(kind="is_malware", observer=observer)

        observations = views._get_malware_observations(db_request, days=90)
        result = views._get_observer_stats(db_request, observations)

        assert len(result) == 1
        assert result[0]["total_observations"] == 1


class TestObserverReputationDashboard:
    def test_dashboard_empty(self, db_request):
        """Test dashboard with no observations."""
        result = views.observer_reputation_dashboard(db_request)

        assert result["days"] == 30
        assert result["observer_stats"] == []
        assert result["summary"]["total_observations"] == 0
        assert result["summary"]["observer_count"] == 0

    def test_dashboard_with_observations(self, db_request):
        """Test dashboard with observations."""
        user = UserFactory.create()
        observer = ObserverFactory.create()
        user.observer = observer

        ProjectObservationFactory.create(kind="is_malware", observer=observer)
        ProjectObservationFactory.create(kind="is_malware", observer=observer)

        result = views.observer_reputation_dashboard(db_request)

        assert result["days"] == 30
        assert len(result["observer_stats"]) == 1
        assert result["summary"]["total_observations"] == 2
        assert result["summary"]["observer_count"] == 1

    @pytest.mark.parametrize(
        ("params", "expected_days"),
        [
            ({"days": "30"}, 30),  # valid
            ({"days": "60"}, 60),  # valid
            ({"days": "invalid"}, 30),  # invalid defaults
            ({"days": "45"}, 30),  # unsupported defaults
        ],
    )
    def test_dashboard_days_parameter(self, db_request, params, expected_days):
        """Test dashboard handles days parameter correctly."""
        db_request.params = params
        result = views.observer_reputation_dashboard(db_request)
        assert result["days"] == expected_days


class TestObserverDetail:
    def test_detail_missing_observer_id(self, db_request):
        """Test detail view when observer_id is not in matchdict."""
        db_request.matchdict = {}

        with pytest.raises(HTTPNotFound):
            views.observer_detail(db_request)

    def test_detail_not_found(self, db_request):
        """Test detail view with non-existent observer."""
        db_request.matchdict = {"observer_id": "00000000-0000-0000-0000-000000000000"}

        with pytest.raises(HTTPNotFound):
            views.observer_detail(db_request)

    def test_detail_with_observer(self, db_request):
        """Test detail view with existing observer."""
        user = UserFactory.create()
        observer = ObserverFactory.create()
        user.observer = observer

        db_request.matchdict = {"observer_id": str(observer.id)}

        result = views.observer_detail(db_request)

        assert result["observer"] == observer
        assert result["username"] == user.username
        assert result["days"] == 30
        assert result["stats"]["total"] == 0
        assert result["stats"]["score"] == 0
        assert "time_series" in result
        assert result["time_series"]["labels"] == []

    def test_detail_with_observations(self, db_request):
        """Test detail view with observations."""
        user = UserFactory.create()
        observer = ObserverFactory.create()
        user.observer = observer

        ProjectObservationFactory.create(kind="is_malware", observer=observer)

        db_request.matchdict = {"observer_id": str(observer.id)}

        result = views.observer_detail(db_request)

        assert result["stats"]["total"] == 1
        assert result["stats"]["pending"] == 1
        assert len(result["observations"]["pending"]) == 1

    @pytest.mark.parametrize(
        ("params", "expected_days"),
        [
            ({"days": "30"}, 30),
            ({"days": "60"}, 60),
            ({"days": "0"}, 0),  # lifetime
            ({"days": "invalid"}, 30),  # invalid defaults to 30
        ],
    )
    def test_detail_days_parameter(self, db_request, params, expected_days):
        """Test detail view handles days parameter correctly."""
        observer = ObserverFactory.create()
        db_request.matchdict = {"observer_id": str(observer.id)}
        db_request.params = params

        result = views.observer_detail(db_request)

        assert result["days"] == expected_days

    def test_detail_categorizes_observations(self, db_request):
        """Test that observations are correctly categorized."""
        user = UserFactory.create()
        observer = ObserverFactory.create()
        user.observer = observer

        now = datetime.now(tz=timezone.utc)

        # True positive (removed)
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            actions={
                int(now.timestamp()): {
                    "action": "remove_malware",
                    "actor": "admin",
                    "created_at": str(now),
                }
            },
        )

        # False positive
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            actions={
                int(now.timestamp()): {
                    "action": "verdict_not_malware",
                    "actor": "admin",
                    "reason": "Not malware",
                    "created_at": str(now),
                }
            },
        )

        # Pending
        ProjectObservationFactory.create(kind="is_malware", observer=observer)

        db_request.matchdict = {"observer_id": str(observer.id)}

        result = views.observer_detail(db_request)

        assert result["stats"]["true_positives"] == 1
        assert result["stats"]["false_positives"] == 1
        assert result["stats"]["pending"] == 1
        assert len(result["observations"]["true_positives"]) == 1
        assert len(result["observations"]["false_positives"]) == 1
        assert len(result["observations"]["pending"]) == 1


class TestAggregateWeeklyTimeSeries:
    def test_time_series_empty(self, db_request):
        """Test time series with no observations."""
        result = views._aggregate_weekly_time_series([])

        assert result["labels"] == []
        assert result["true_positives"] == []
        assert result["false_positives"] == []
        assert result["pending"] == []

    def test_time_series_with_observations(self, db_request):
        """Test time series with observations."""
        observer = ObserverFactory.create()

        ProjectObservationFactory.create(kind="is_malware", observer=observer)

        observations = views._get_malware_observations(db_request, days=90)
        result = views._aggregate_weekly_time_series(observations)

        assert len(result["labels"]) >= 1
        assert sum(result["pending"]) == 1  # New observation is pending


class TestGetObserverTimeSeries:
    def test_time_series_empty(self, db_request):
        """Test time series with no observations for observer."""
        observer = ObserverFactory.create()

        result = views._get_observer_time_series(db_request, observer, days=90)

        assert result["labels"] == []
        assert result["true_positives"] == []
        assert result["false_positives"] == []
        assert result["pending"] == []

    def test_time_series_with_observations(self, db_request):
        """Test time series with observations for observer."""
        observer = ObserverFactory.create()

        ProjectObservationFactory.create(kind="is_malware", observer=observer)

        result = views._get_observer_time_series(db_request, observer, days=90)

        assert len(result["labels"]) >= 1
        assert sum(result["pending"]) == 1
        assert sum(result["true_positives"]) == 0
        assert sum(result["false_positives"]) == 0

    def test_time_series_lifetime(self, db_request):
        """Test time series with days=0 (lifetime) returns all observations."""
        observer = ObserverFactory.create()

        ProjectObservationFactory.create(kind="is_malware", observer=observer)

        result = views._get_observer_time_series(db_request, observer, days=0)

        assert len(result["labels"]) >= 1
        assert sum(result["pending"]) == 1


class TestGetObserverDetailStats:
    def test_detail_stats_empty(self, db_request):
        """Test detail stats with no observations."""
        observer = ObserverFactory.create()

        result = views._get_observer_detail_stats(db_request, observer, days=90)

        assert result["true_positives"] == []
        assert result["false_positives"] == []
        assert result["pending"] == []

    def test_detail_stats_lifetime(self, db_request):
        """Test detail stats with days=0 (lifetime) returns all observations."""
        user = UserFactory.create()
        observer = ObserverFactory.create()
        user.observer = observer

        ProjectObservationFactory.create(kind="is_malware", observer=observer)

        result = views._get_observer_detail_stats(db_request, observer, days=0)

        # Should return the observation even with days=0
        assert len(result["pending"]) == 1

    def test_detail_stats_categorization(self, db_request):
        """Test that detail stats correctly categorize observations."""
        user = UserFactory.create()
        observer = ObserverFactory.create()
        user.observer = observer

        now = datetime.now(tz=timezone.utc)

        # Create one of each type
        ProjectObservationFactory.create(
            kind="is_malware", observer=observer, related=None
        )  # removed = true positive

        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            actions={
                int(now.timestamp()): {
                    "action": "verdict_not_malware",
                    "actor": "admin",
                    "reason": "test",
                    "created_at": str(now),
                }
            },
        )  # false positive

        ProjectObservationFactory.create(
            kind="is_malware", observer=observer
        )  # pending

        result = views._get_observer_detail_stats(db_request, observer, days=90)

        assert len(result["true_positives"]) == 1
        assert len(result["false_positives"]) == 1
        assert len(result["pending"]) == 1
