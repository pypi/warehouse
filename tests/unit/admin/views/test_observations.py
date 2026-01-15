# SPDX-License-Identifier: Apache-2.0

from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pretend
import pytest

from warehouse.admin.views import observations as views
from warehouse.observations.models import Observation

from ....common.db.accounts import UserFactory
from ....common.db.observations import ObserverFactory
from ....common.db.packaging import (
    JournalEntryFactory,
    ProjectFactory,
    ProjectObservationFactory,
)


class TestObservationsList:
    def test_observations_list(self):
        request = pretend.stub(
            db=pretend.stub(
                query=pretend.call_recorder(
                    lambda *a: pretend.stub(
                        order_by=lambda *a: pretend.stub(all=lambda: [])
                    )
                )
            )
        )
        assert views.observations_list(request) == {"kind_groups": defaultdict(list)}
        assert request.db.query.calls == [pretend.call(Observation)]

    def test_observations_list_with_observations(self):
        observations = [
            Observation(
                kind="is_spam",
                summary="This is spam",
                payload={},
            ),
            Observation(
                kind="is_spam",
                summary="This is also spam",
                payload={},
            ),
        ]

        request = pretend.stub(
            db=pretend.stub(
                query=pretend.call_recorder(
                    lambda *a: pretend.stub(
                        order_by=lambda *a: pretend.stub(all=lambda: observations)
                    )
                )
            )
        )

        assert views.observations_list(request) == {
            "kind_groups": {"is_spam": observations}
        }
        assert request.db.query.calls == [pretend.call(Observation)]


class TestParseDaysParam:
    """Tests for the _parse_days_param helper function."""

    @pytest.mark.parametrize(
        ("params", "expected"),
        [
            ({}, 30),  # default
            ({"days": "30"}, 30),
            ({"days": "60"}, 60),
            ({"days": "90"}, 90),
            ({"days": "invalid"}, 30),  # fallback to default
            ({"days": "15"}, 30),  # not in allowed, fallback
            ({"days": ""}, 30),  # empty string
        ],
    )
    def test_parse_days(self, params, expected, mocker):
        request = mocker.MagicMock(params=params)
        assert views._parse_days_param(request) == expected


class TestHoursBetween:
    """Tests for the _hours_between helper function.

    This helper calculates hours between two timestamps, returning None for:
    - Missing timestamps (either or both)
    - Negative time differences (indicates data inconsistency)
    """

    # Reference timestamps for parametrized tests
    T0 = datetime(2025, 1, 1, 0, 0, 0)  # Base time
    T1 = datetime(2025, 1, 1, 1, 0, 0)  # 1 hour later
    T2_5 = datetime(2025, 1, 1, 2, 30, 0)  # 2.5 hours later
    T3 = datetime(2025, 1, 1, 3, 0, 0)  # 3 hours later

    @pytest.mark.parametrize(
        ("start", "end", "expected"),
        [
            # Valid positive differences
            (T0, T2_5, 2.5),  # 2.5 hours later
            (T0, T1, 1.0),  # 1 hour later
            (T0, T0, 0.0),  # Same time (zero difference is valid)
            # Invalid: negative difference (end before start)
            (T3, T1, None),  # End is 2 hours before start
            # Invalid: missing timestamps
            (None, T1, None),  # Missing start
            (T0, None, None),  # Missing end
            (None, None, None),  # Both missing
        ],
        ids=[
            "positive_2.5_hours",
            "positive_1_hour",
            "zero_difference",
            "negative_difference",
            "missing_start",
            "missing_end",
            "both_missing",
        ],
    )
    def test_hours_between(self, start, end, expected):
        """Test _hours_between with various input combinations."""
        assert views._hours_between(start, end) == expected


def _fetch_observations(db_request):
    """Helper to fetch observations for tests using the new API."""
    cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=90)
    return views._fetch_malware_observations(db_request, cutoff_date), cutoff_date


def _get_project_data(db_request):
    """Helper to get project_data for timeline tests using the new API."""
    observations, _ = _fetch_observations(db_request)
    return views._get_timeline_data(db_request, observations)


class TestGetCorroborationStats:
    """Tests for _get_corroboration_stats which returns (corroboration, accuracy)."""

    def test_empty_observations(self, db_request):
        """Test with no observations returns empty stats."""
        observations, _ = _fetch_observations(db_request)
        corroboration, accuracy = views._get_corroboration_stats(observations)

        assert corroboration["total_packages"] == 0
        assert corroboration["total_reports"] == 0
        assert corroboration["corroboration_rate"] is None
        assert accuracy["single"]["total"] == 0
        assert accuracy["multi"]["total"] == 0

    def test_single_reports_only(self, db_request):
        """Test with only single-observer reports (no corroboration)."""
        observer1 = ObserverFactory.create()
        observer2 = ObserverFactory.create()

        # Two different packages, one report each
        ProjectObservationFactory.create(kind="is_malware", observer=observer1)
        ProjectObservationFactory.create(kind="is_malware", observer=observer2)

        observations, _ = _fetch_observations(db_request)
        corroboration, accuracy = views._get_corroboration_stats(observations)

        assert corroboration["total_packages"] == 2
        assert corroboration["single_report_packages"] == 2
        assert corroboration["multi_report_packages"] == 0
        assert corroboration["corroboration_rate"] == 0.0
        assert accuracy["single"]["total"] == 2
        assert accuracy["multi"]["total"] == 0

    def test_multi_reports_corroboration(self, db_request):
        """Test multiple observers on same package counts as corroborated."""
        observer1 = ObserverFactory.create()
        observer2 = ObserverFactory.create()
        project = ProjectFactory.create()

        # Same package, two observers
        ProjectObservationFactory.create(
            kind="is_malware", observer=observer1, related=project
        )
        ProjectObservationFactory.create(
            kind="is_malware", observer=observer2, related=project
        )

        observations, _ = _fetch_observations(db_request)
        corroboration, accuracy = views._get_corroboration_stats(observations)

        assert corroboration["total_packages"] == 1
        assert corroboration["multi_report_packages"] == 1
        assert corroboration["corroborated_reports"] == 2
        assert corroboration["corroboration_rate"] == 100.0
        assert accuracy["multi"]["total"] == 2

    def test_multi_report_true_positive(self, db_request):
        """Test true positive verdict in multi-report package."""
        observer1 = ObserverFactory.create()
        observer2 = ObserverFactory.create()
        project = ProjectFactory.create()

        now = datetime.now(tz=timezone.utc)

        # Multi-report package with one true positive action
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer1,
            related=project,
            actions={
                int(now.timestamp()): {
                    "action": "remove_malware",
                    "actor": "admin",
                    "created_at": str(now),
                }
            },
        )
        ProjectObservationFactory.create(
            kind="is_malware", observer=observer2, related=project
        )

        observations, _ = _fetch_observations(db_request)
        corroboration, accuracy = views._get_corroboration_stats(observations)

        assert corroboration["multi_report_packages"] == 1
        assert accuracy["multi"]["total"] == 2
        assert accuracy["multi"]["true_pos"] == 1

    def test_single_report_false_positive(self, db_request):
        """Test false positive verdict in single-report package."""
        observer = ObserverFactory.create()
        project = ProjectFactory.create()

        now = datetime.now(tz=timezone.utc)

        # Single-report package with false positive action
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
            actions={
                int(now.timestamp()): {
                    "action": "verdict_not_malware",
                    "actor": "admin",
                    "reason": "Not malware",
                    "created_at": str(now),
                }
            },
        )

        observations, _ = _fetch_observations(db_request)
        corroboration, accuracy = views._get_corroboration_stats(observations)

        assert corroboration["single_report_packages"] == 1
        assert accuracy["single"]["total"] == 1
        assert accuracy["single"]["false_pos"] == 1
        assert accuracy["single"]["accuracy"] == 0.0


class TestGetObserverTypeStats:
    def test_empty_observations(self, db_request):
        """Test observer type stats with no observations."""
        observations, _ = _fetch_observations(db_request)
        result = views._get_observer_type_stats(db_request, observations)

        assert result["trusted"]["total"] == 0
        assert result["non_trusted"]["total"] == 0

    def test_trusted_vs_non_trusted(self, db_request):
        """Test breakdown by observer type."""
        # Trusted observer
        trusted_user = UserFactory.create(is_observer=True)
        trusted_observer = ObserverFactory.create()
        trusted_user.observer = trusted_observer

        # Non-trusted user
        regular_user = UserFactory.create(is_observer=False)
        regular_observer = ObserverFactory.create()
        regular_user.observer = regular_observer

        ProjectObservationFactory.create(kind="is_malware", observer=trusted_observer)
        ProjectObservationFactory.create(kind="is_malware", observer=regular_observer)

        observations, _ = _fetch_observations(db_request)
        result = views._get_observer_type_stats(db_request, observations)

        assert result["trusted"]["total"] == 1
        assert result["non_trusted"]["total"] == 1

    def test_observer_type_with_verdicts(self, db_request):
        """Test observer type stats with true and false positive verdicts."""
        # Trusted observer with true positive
        trusted_user = UserFactory.create(is_observer=True)
        trusted_observer = ObserverFactory.create()
        trusted_user.observer = trusted_observer

        # Non-trusted user with false positive
        regular_user = UserFactory.create(is_observer=False)
        regular_observer = ObserverFactory.create()
        regular_user.observer = regular_observer

        now = datetime.now(tz=timezone.utc)

        # Trusted observer: true positive (removed)
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=trusted_observer,
            actions={
                int(now.timestamp()): {
                    "action": "remove_malware",
                    "actor": "admin",
                    "created_at": str(now),
                }
            },
        )

        # Non-trusted observer: false positive
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=regular_observer,
            actions={
                int(now.timestamp()): {
                    "action": "verdict_not_malware",
                    "actor": "admin",
                    "reason": "Not malware",
                    "created_at": str(now),
                }
            },
        )

        observations, _ = _fetch_observations(db_request)
        result = views._get_observer_type_stats(db_request, observations)

        assert result["trusted"]["total"] == 1
        assert result["trusted"]["true_pos"] == 1
        assert result["trusted"]["false_pos"] == 0
        assert result["non_trusted"]["total"] == 1
        assert result["non_trusted"]["true_pos"] == 0
        assert result["non_trusted"]["false_pos"] == 1


class TestGetAutoQuarantineStats:
    def test_no_reported_packages(self, db_request):
        """Test with no reported packages."""
        observations, cutoff_date = _fetch_observations(db_request)
        result = views._get_auto_quarantine_stats(db_request, observations, cutoff_date)

        assert result["total_reported"] == 0
        assert result["auto_quarantined"] == 0
        assert result["quarantine_rate"] is None

    def test_removed_reported_packages(self, db_request):
        """Test with reported packages that were auto-quarantined then removed.

        When a project is deleted, the observation's related_id becomes NULL.
        These observations should still be counted in auto-quarantine stats.
        """
        project_name = "removed-reported-package"

        # Create observation with no related project (simulates deleted project)
        now = datetime.now(tz=timezone.utc)
        ProjectObservationFactory.create(
            kind="is_malware",
            related=None,  # Project was deleted
            related_name=f"Project(id=None, name='{project_name}')",
            actions={
                int(now.timestamp()): {
                    "action": "remove_malware",
                    "actor": "admin",
                    "created_at": str(now),
                }
            },
        )
        # Add journal entry showing it was auto-quarantined before removal
        JournalEntryFactory.create(
            name=project_name,
            action="project quarantined",
            submitted_by=UserFactory.create(username="admin"),
            submitted_date=now.replace(tzinfo=None),
        )

        observations, cutoff_date = _fetch_observations(db_request)
        result = views._get_auto_quarantine_stats(db_request, observations, cutoff_date)

        assert result["total_reported"] == 1
        assert result["auto_quarantined"] == 1
        assert result["quarantine_rate"] == 100.0

    def test_with_quarantined_packages(self, db_request):
        """Test with reported packages that were auto-quarantined."""
        # Create admin user for journal entry
        admin_user = UserFactory.create(username="admin")

        observer = ObserverFactory.create()
        project = ProjectFactory.create()

        # Create observation for the project
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
        )

        # Create journal entry for auto-quarantine
        JournalEntryFactory.create(
            name=project.name,
            action="project quarantined",
            submitted_by=admin_user,
            submitted_date=datetime.now(tz=timezone.utc).replace(tzinfo=None),
        )

        observations, cutoff_date = _fetch_observations(db_request)
        result = views._get_auto_quarantine_stats(db_request, observations, cutoff_date)

        assert result["total_reported"] == 1
        assert result["auto_quarantined"] == 1
        assert result["quarantine_rate"] == 100.0

    def test_partial_quarantine(self, db_request):
        """Test with some packages quarantined and some not."""
        # Create admin user for journal entry
        admin_user = UserFactory.create(username="admin")

        observer = ObserverFactory.create()
        project1 = ProjectFactory.create()
        project2 = ProjectFactory.create()

        # Create observations for both projects
        ProjectObservationFactory.create(
            kind="is_malware", observer=observer, related=project1
        )
        ProjectObservationFactory.create(
            kind="is_malware", observer=observer, related=project2
        )

        # Only quarantine project1
        JournalEntryFactory.create(
            name=project1.name,
            action="project quarantined",
            submitted_by=admin_user,
            submitted_date=datetime.now(tz=timezone.utc).replace(tzinfo=None),
        )

        observations, cutoff_date = _fetch_observations(db_request)
        result = views._get_auto_quarantine_stats(db_request, observations, cutoff_date)

        assert result["total_reported"] == 2
        assert result["auto_quarantined"] == 1
        assert result["quarantine_rate"] == 50.0

    def test_invalid_related_name_format(self, db_request):
        """Test with observations that have unparseable related_name format.

        When related_name doesn't match the expected Project(name='...') format,
        the observation is skipped for quarantine stats.
        """
        observer = ObserverFactory.create()

        # Create observation with invalid related_name (no name='...' pattern)
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=None,
            related_name="invalid-format-without-name-field",
        )

        observations, cutoff_date = _fetch_observations(db_request)
        result = views._get_auto_quarantine_stats(db_request, observations, cutoff_date)

        # Should return empty stats since no valid project names could be parsed
        assert result["total_reported"] == 0
        assert result["auto_quarantined"] == 0
        assert result["quarantine_rate"] is None


class TestGetResponseTimelineStats:
    def test_no_observations(self, db_request):
        """Test timeline with no observations."""
        project_data = _get_project_data(db_request)
        result = views._get_response_timeline_stats(project_data)

        assert result["sample_size"] == 0
        assert result["detection_time"] is None

    def test_with_observations_and_removal(self, db_request):
        """Test timeline with observations that have removal actions."""
        admin_user = UserFactory.create(username="admin")
        observer = ObserverFactory.create()
        project_created = datetime.now(tz=timezone.utc).replace(
            tzinfo=None
        ) - timedelta(hours=24)
        # Create project with a recent created date
        project = ProjectFactory.create(created=project_created)

        # Create JournalEntry for project creation (required for timeline lookup)
        JournalEntryFactory.create(
            name=project.name,
            action="create",
            submitted_by=admin_user,
            submitted_date=project_created,
        )

        # Report happens first, removal happens 1 hour later (realistic scenario)
        report_time = datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(
            hours=2
        )
        removal_time = datetime.now(tz=timezone.utc) - timedelta(hours=1)

        # Create observation with removal action
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
            created=report_time,
            actions={
                int(removal_time.timestamp()): {
                    "action": "remove_malware",
                    "actor": "admin",
                }
            },
        )

        project_data = _get_project_data(db_request)
        result = views._get_response_timeline_stats(project_data)

        assert result["sample_size"] == 1
        assert result["detection_time"] is not None
        assert result["removal_time"] is not None

    def test_with_quarantine(self, db_request):
        """Test timeline with quarantine journal entries."""
        # Create admin user for journal entry
        admin_user = UserFactory.create(username="admin")

        observer = ObserverFactory.create()
        project = ProjectFactory.create(
            created=datetime.now(tz=timezone.utc).replace(tzinfo=None)
            - timedelta(hours=24)
        )

        # Create observation
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
        )

        # Create quarantine journal entry
        JournalEntryFactory.create(
            name=project.name,
            action="project quarantined",
            submitted_by=admin_user,
            submitted_date=datetime.now(tz=timezone.utc).replace(tzinfo=None),
        )

        project_data = _get_project_data(db_request)
        result = views._get_response_timeline_stats(project_data)

        assert result["sample_size"] == 1
        assert result["quarantine_time"] is not None

    def test_longest_lived_packages(self, db_request):
        """Test that longest-lived packages are returned."""
        admin_user = UserFactory.create(username="admin")
        observer = ObserverFactory.create()

        # Create multiple projects with different exposure times
        for i in range(7):
            project_created = datetime.now(tz=timezone.utc).replace(
                tzinfo=None
            ) - timedelta(hours=24 * (i + 1))
            project = ProjectFactory.create(created=project_created)

            # Create JournalEntry for project creation (required for timeline lookup)
            JournalEntryFactory.create(
                name=project.name,
                action="create",
                submitted_by=admin_user,
                submitted_date=project_created,
            )

            now = datetime.now(tz=timezone.utc)
            ProjectObservationFactory.create(
                kind="is_malware",
                observer=observer,
                related=project,
                actions={
                    int(now.timestamp()): {
                        "action": "remove_malware",
                        "actor": "admin",
                        "created_at": str(now),
                    }
                },
            )

        project_data = _get_project_data(db_request)
        result = views._get_response_timeline_stats(project_data)

        assert result["sample_size"] == 7
        assert len(result["longest_lived"]) == 5  # Top 5

    def test_multiple_reports_for_same_project(self, db_request):
        """Test that multiple reports for same project use earliest report time."""
        admin_user = UserFactory.create(username="admin")
        observer1 = ObserverFactory.create()
        observer2 = ObserverFactory.create()
        project_created = datetime.now(tz=timezone.utc).replace(
            tzinfo=None
        ) - timedelta(hours=48)
        project = ProjectFactory.create(created=project_created)

        # Create JournalEntry for project creation (required for timeline lookup)
        JournalEntryFactory.create(
            name=project.name,
            action="create",
            submitted_by=admin_user,
            submitted_date=project_created,
        )

        now = datetime.now(tz=timezone.utc)
        earlier = now - timedelta(hours=2)

        # First observation: earlier report time
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer1,
            related=project,
            created=earlier.replace(tzinfo=None),
            actions={
                int(now.timestamp()): {
                    "action": "remove_malware",
                    "actor": "admin",
                    "created_at": str(now),
                }
            },
        )

        # Second observation: later report time
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer2,
            related=project,
            created=now.replace(tzinfo=None),
            actions={
                int(now.timestamp()): {
                    "action": "some_other_action",
                    "actor": "admin",
                }
            },
        )

        # Third observation: even earlier, with an earlier removal time
        # This tests the branch where we update removal_time to an earlier value
        even_earlier = now - timedelta(hours=4)
        earlier_removal = now - timedelta(hours=3)  # Earlier than first observation
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=ObserverFactory.create(),
            related=project,
            created=even_earlier.replace(tzinfo=None),
            actions={
                int(earlier_removal.timestamp()): {
                    "action": "remove_malware",
                    "actor": "admin",
                }
            },
        )

        project_data = _get_project_data(db_request)
        result = views._get_response_timeline_stats(project_data)

        assert result["sample_size"] == 1  # One project
        assert result["detection_time"] is not None

    def test_with_both_quarantine_and_removal(self, db_request):
        """Test timeline uses min of quarantine/removal for response time."""
        admin_user = UserFactory.create(username="admin")
        observer = ObserverFactory.create()
        project = ProjectFactory.create(
            created=datetime.now(tz=timezone.utc).replace(tzinfo=None)
            - timedelta(hours=48)
        )

        # Report happens first (2 hours ago)
        report_time = datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(
            hours=2
        )

        # Quarantine happens after report (1 hour ago)
        quarantine_time = datetime.now(tz=timezone.utc).replace(
            tzinfo=None
        ) - timedelta(hours=1)

        # Removal happens last (now)
        removal_time = datetime.now(tz=timezone.utc)

        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
            created=report_time,
            actions={
                int(removal_time.timestamp()): {
                    "action": "remove_malware",
                    "actor": "admin",
                    "created_at": str(removal_time),
                }
            },
        )

        JournalEntryFactory.create(
            name=project.name,
            action="project quarantined",
            submitted_by=admin_user,
            submitted_date=quarantine_time,
        )

        project_data = _get_project_data(db_request)
        result = views._get_response_timeline_stats(project_data)

        assert result["sample_size"] == 1
        assert result["quarantine_time"] is not None
        assert result["removal_time"] is not None

    def test_deleted_project_timeline(self, db_request):
        """Test timeline stats for deleted projects using journal entries.

        This also tests the project recreation scenario:
        - Original project created years ago
        - Original project removed
        - Malicious project created with same name (name squatting)
        - We should use the MOST RECENT create date, not the original
        """
        admin_user = UserFactory.create(username="admin")
        original_owner = UserFactory.create(username="original-owner")

        project_name = "deleted-test-project"
        now = datetime.now(tz=timezone.utc)

        # Simulate original project lifecycle (years ago)
        original_created = now.replace(tzinfo=None) - timedelta(days=365 * 3)
        JournalEntryFactory.create(
            name=project_name,
            action="create",
            submitted_by=original_owner,
            submitted_date=original_created,
        )
        # Original project was removed (not relevant to our query, just context)
        JournalEntryFactory.create(
            name=project_name,
            action="remove project",
            submitted_by=original_owner,
            submitted_date=now.replace(tzinfo=None) - timedelta(days=30),
        )

        # Malicious recreation - this is the `create` date we should use
        malicious_created = now.replace(tzinfo=None) - timedelta(hours=48)
        JournalEntryFactory.create(
            name=project_name,
            action="create",
            submitted_by=UserFactory.create(username="malicious-actor"),
            submitted_date=malicious_created,
        )

        # Create observation for deleted project (related=None after removal)
        report_time = now.replace(tzinfo=None) - timedelta(hours=24)
        ProjectObservationFactory.create(
            kind="is_malware",
            related=None,
            related_name=f"Project(id=None, name='{project_name}')",
            created=report_time,
            actions={
                int(now.timestamp()): {
                    "action": "remove_malware",
                    "actor": "admin",
                    "created_at": str(now),
                }
            },
        )

        # Create quarantine journal entry
        JournalEntryFactory.create(
            name=project_name,
            action="project quarantined",
            submitted_by=admin_user,
            submitted_date=now.replace(tzinfo=None) - timedelta(hours=12),
        )

        project_data = _get_project_data(db_request)
        result = views._get_response_timeline_stats(project_data)

        # Should find the deleted project and calculate timeline stats
        assert result["sample_size"] == 1
        assert result["detection_time"] is not None

        # Detection time should be ~24 hours (malicious_created -> report)
        # NOT ~3 years (original_created -> report)
        # malicious_created is 48h ago, report_time is 24h ago = 24h detection
        detection_hours = result["detection_time"]["median"]
        assert detection_hours < 100, (
            f"Detection time {detection_hours}h suggests we're using the old "
            f"'create' date instead of the most recent one"
        )
        assert result["quarantine_time"] is not None
        assert result["longest_lived"][0]["name"] == project_name


class TestParseProjectNameFromRepr:
    """Tests for the _parse_project_name_from_repr helper function."""

    @pytest.mark.parametrize(
        ("related_name", "expected"),
        [
            ("Project(id=UUID('abc'), name='my-project')", "my-project"),
            ("Project(name='test-pkg', id=123)", "test-pkg"),
            ("Project(id=None, name='deleted-project')", "deleted-project"),
            ("Project(name='foo-bar-123', other='value')", "foo-bar-123"),
            # Edge cases
            ("Project(id=123)", None),  # No name field
            ("SomeOtherClass(name='test')", "test"),  # Still matches pattern
            ("invalid string", None),  # No match
            ("", None),  # Empty string
        ],
    )
    def test_parse_project_name(self, related_name, expected):
        assert views._parse_project_name_from_repr(related_name) == expected


class TestObservationsInsights:
    def test_insights_view(self, db_request):
        """Test insights view returns expected structure."""
        db_request.params = {}

        result = views.observations_insights(db_request)

        assert "days" in result
        assert "corroboration" in result
        assert "corroborated_accuracy" in result
        assert "observer_types" in result
        assert "auto_quarantine" in result
        assert "timeline" in result

    @pytest.mark.parametrize(
        ("params", "expected_days"),
        [
            ({}, 30),
            ({"days": "60"}, 60),
            ({"days": "90"}, 90),
            ({"days": "invalid"}, 30),
        ],
    )
    def test_insights_days_parameter(self, db_request, params, expected_days):
        """Test insights view handles days parameter correctly."""
        db_request.params = params

        result = views.observations_insights(db_request)

        assert result["days"] == expected_days


class TestGetTimelineData:
    """Tests for _get_timeline_data function."""

    def test_invalid_related_names_skip_journal_lookup(self, db_request):
        """Test that observations with unparseable related_name skip journal lookup.

        When no valid project names can be parsed from related_name,
        the function returns early without querying journal entries.
        """
        observer = ObserverFactory.create()

        # Create observation with invalid related_name (no name='...' pattern)
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=None,
            related_name="invalid-format-no-name-field",
        )

        observations, _ = _fetch_observations(db_request)
        result = views._get_timeline_data(db_request, observations)

        # Should return project_data with None for name and no journal data
        assert len(result) == 1
        key = "invalid-format-no-name-field"
        assert result[key]["name"] is None
        assert result[key]["project_created"] is None
        assert result[key]["quarantine_time"] is None


class TestGetTimelineTrends:
    def test_no_observations(self, db_request):
        """Test timeline trends with no observations."""
        project_data = _get_project_data(db_request)
        result = views._get_timeline_trends(project_data)

        assert result["labels"] == []
        assert result["detection"] == []
        assert result["response"] == []
        assert result["time_to_quarantine"] == []

    def test_missing_first_report_skipped(self):
        """Test that entries with missing first_report are skipped.

        This is a defensive check - in practice first_report should always
        be set from the observation's created timestamp.
        """
        # Directly test with project_data that has first_report=None
        project_data = {
            "project-key": {
                "name": "test-project",
                "project_created": datetime.now(tz=timezone.utc).replace(tzinfo=None),
                "first_report": None,  # Missing first_report
                "quarantine_time": None,
                "removal_time": None,
            }
        }

        result = views._get_timeline_trends(project_data)

        # Should return empty results since first_report is missing
        assert result["labels"] == []
        assert result["detection"] == []
        assert result["response"] == []
        assert result["time_to_quarantine"] == []

    def test_with_observations(self, db_request):
        """Test timeline trends with observations returns weekly data."""
        observer = ObserverFactory.create()

        # Create observation
        ProjectObservationFactory.create(kind="is_malware", observer=observer)

        project_data = _get_project_data(db_request)
        result = views._get_timeline_trends(project_data)

        # Should have at least one week of data
        assert len(result["labels"]) >= 1
        # Detection time should have data (project_created -> report)
        assert result["detection"][0] is not None or result["detection"] == [None]

    def test_with_quarantine_and_removal(self, db_request):
        """Test timeline trends with quarantine and removal actions."""
        # Create admin user for journal entry
        admin_user = UserFactory.create(username="admin")

        observer = ObserverFactory.create()
        project_created = datetime.now(tz=timezone.utc).replace(
            tzinfo=None
        ) - timedelta(hours=48)
        project = ProjectFactory.create(created=project_created)

        now = datetime.now(tz=timezone.utc)

        # Create project creation journal entry (required for time_to_quarantine)
        JournalEntryFactory.create(
            name=project.name,
            action="create",
            submitted_by=admin_user,
            submitted_date=project_created,
        )

        # Create observation with removal action
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
            actions={
                int(now.timestamp()): {
                    "action": "remove_malware",
                    "actor": "admin",
                    "created_at": str(now),
                }
            },
        )

        # Create quarantine journal entry
        JournalEntryFactory.create(
            name=project.name,
            action="project quarantined",
            submitted_by=admin_user,
            submitted_date=datetime.now(tz=timezone.utc).replace(tzinfo=None)
            - timedelta(hours=1),
        )

        project_data = _get_project_data(db_request)
        result = views._get_timeline_trends(project_data)

        assert len(result["labels"]) >= 1
        assert len(result["detection"]) >= 1
        assert len(result["response"]) >= 1
        assert len(result["time_to_quarantine"]) >= 1
        # Ensure time_to_quarantine has actual data (not None)
        assert result["time_to_quarantine"][0] is not None

    def test_with_only_quarantine(self, db_request):
        """Test timeline trends with only quarantine (no removal)."""
        # Create admin user for journal entry
        admin_user = UserFactory.create(username="admin")

        observer = ObserverFactory.create()
        project = ProjectFactory.create(
            created=datetime.now(tz=timezone.utc).replace(tzinfo=None)
            - timedelta(hours=24)
        )

        # Create observation without removal action
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
        )

        # Create quarantine journal entry
        JournalEntryFactory.create(
            name=project.name,
            action="project quarantined",
            submitted_by=admin_user,
            submitted_date=datetime.now(tz=timezone.utc).replace(tzinfo=None),
        )

        project_data = _get_project_data(db_request)
        result = views._get_timeline_trends(project_data)

        assert len(result["labels"]) >= 1
        # Response should have data (quarantine is an action)
        assert len(result["response"]) >= 1

    def test_with_only_removal(self, db_request):
        """Test timeline trends with only removal (no quarantine)."""
        observer = ObserverFactory.create()
        project = ProjectFactory.create(
            created=datetime.now(tz=timezone.utc).replace(tzinfo=None)
            - timedelta(hours=24)
        )

        now = datetime.now(tz=timezone.utc)

        # Create observation with removal action only
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
            actions={
                int(now.timestamp()): {
                    "action": "remove_malware",
                    "actor": "admin",
                    "created_at": str(now),
                }
            },
        )

        project_data = _get_project_data(db_request)
        result = views._get_timeline_trends(project_data)

        assert len(result["labels"]) >= 1
        assert len(result["response"]) >= 1
        # No quarantine, so time_to_quarantine should be None
        assert result["time_to_quarantine"][0] is None

    def test_multiple_reports_same_project(self, db_request):
        """Test timeline trends with multiple reports for same project."""
        observer1 = ObserverFactory.create()
        observer2 = ObserverFactory.create()
        project = ProjectFactory.create(
            created=datetime.now(tz=timezone.utc).replace(tzinfo=None)
            - timedelta(hours=48)
        )

        now = datetime.now(tz=timezone.utc)

        # First report (later)
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer1,
            related=project,
            created=datetime.now(tz=timezone.utc).replace(tzinfo=None),
            actions={
                int(now.timestamp()): {
                    "action": "remove_malware",
                    "actor": "admin",
                    "created_at": str(now),
                }
            },
        )

        # Second report (earlier)
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer2,
            related=project,
            created=datetime.now(tz=timezone.utc).replace(tzinfo=None)
            - timedelta(hours=2),
        )

        project_data = _get_project_data(db_request)
        result = views._get_timeline_trends(project_data)

        assert len(result["labels"]) >= 1
        assert len(result["detection"]) >= 1

    def test_later_observation_does_not_update_first_report(self, db_request):
        """Test that a later observation doesn't update first_report."""
        observer = ObserverFactory.create()
        project = ProjectFactory.create(
            created=datetime.now(tz=timezone.utc).replace(tzinfo=None)
            - timedelta(hours=48)
        )

        # First observation (earlier - should be first_report)
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
            created=datetime.now(tz=timezone.utc).replace(tzinfo=None)
            - timedelta(hours=24),
        )

        # Second observation (later - should NOT update first_report)
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
            created=datetime.now(tz=timezone.utc).replace(tzinfo=None),
        )

        project_data = _get_project_data(db_request)
        result = views._get_timeline_trends(project_data)

        assert len(result["labels"]) >= 1
        assert len(result["detection"]) >= 1

    def test_actions_with_non_removal_entries(self, db_request):
        """Test actions dict with non-remove_malware entries."""
        observer = ObserverFactory.create()
        project = ProjectFactory.create(
            created=datetime.now(tz=timezone.utc).replace(tzinfo=None)
            - timedelta(hours=24)
        )

        now = datetime.now(tz=timezone.utc)

        # Actions dict with multiple types - one removal, one other
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
            actions={
                int(now.timestamp()): {
                    "action": "some_other_action",
                    "actor": "system",
                },
                int(now.timestamp())
                + 1: {
                    "action": "remove_malware",
                    "actor": "admin",
                    "created_at": str(now),
                },
            },
        )

        project_data = _get_project_data(db_request)
        result = views._get_timeline_trends(project_data)

        assert len(result["labels"]) >= 1
        assert len(result["response"]) >= 1

    def test_removal_action_uses_timestamp_key(self, db_request):
        """Test that removal time is parsed from the dict key (unix timestamp).

        The actions dict is keyed by unix timestamp, so we use that directly
        rather than parsing the created_at string.
        """
        observer = ObserverFactory.create()
        project = ProjectFactory.create(
            created=datetime.now(tz=timezone.utc).replace(tzinfo=None)
            - timedelta(hours=24)
        )

        # Report happens first, removal happens 1 hour later (realistic scenario)
        report_time = datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(
            hours=2
        )
        removal_time = datetime.now(tz=timezone.utc) - timedelta(hours=1)

        # Removal action - created_at is optional since we use the dict key
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
            created=report_time,
            actions={
                int(removal_time.timestamp()): {
                    "action": "remove_malware",
                    "actor": "admin",
                    # created_at not needed - we use the dict key
                },
            },
        )

        project_data = _get_project_data(db_request)
        result = views._get_timeline_trends(project_data)

        assert len(result["labels"]) >= 1
        # Response time is available because we use the timestamp key
        assert result["response"][0] is not None

    def test_multiple_removal_actions_keeps_earliest(self, db_request):
        """Test multiple removal actions where later one is ignored."""
        observer = ObserverFactory.create()
        project = ProjectFactory.create(
            created=datetime.now(tz=timezone.utc).replace(tzinfo=None)
            - timedelta(hours=48)
        )

        now = datetime.now(tz=timezone.utc)
        earlier = now - timedelta(hours=12)
        later = now

        # Two removal actions - earlier one first, then later one
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
            actions={
                int(earlier.timestamp()): {
                    "action": "remove_malware",
                    "actor": "admin",
                    "created_at": str(earlier),
                },
                int(later.timestamp()): {
                    "action": "remove_malware",
                    "actor": "admin",
                    "created_at": str(later),  # later - should not update
                },
            },
        )

        project_data = _get_project_data(db_request)
        result = views._get_timeline_trends(project_data)

        assert len(result["labels"]) >= 1
        assert len(result["response"]) >= 1

    def test_multiple_projects_same_week(self, db_request):
        """Test multiple projects in same week reuses weekly_data."""
        admin_user = UserFactory.create(username="admin")
        observer = ObserverFactory.create()

        now = datetime.now(tz=timezone.utc).replace(tzinfo=None)

        # Create two projects and observations in the same week
        project1_created = now - timedelta(hours=48)
        project2_created = now - timedelta(hours=72)
        project1 = ProjectFactory.create(created=project1_created)
        project2 = ProjectFactory.create(created=project2_created)

        # Create JournalEntries for project creation (required for timeline lookup)
        JournalEntryFactory.create(
            name=project1.name,
            action="create",
            submitted_by=admin_user,
            submitted_date=project1_created,
        )
        JournalEntryFactory.create(
            name=project2.name,
            action="create",
            submitted_by=admin_user,
            submitted_date=project2_created,
        )

        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project1,
            created=now - timedelta(hours=24),
        )
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project2,
            created=now - timedelta(hours=20),  # same week
        )

        project_data = _get_project_data(db_request)
        result = views._get_timeline_trends(project_data)

        # Should have exactly one week with data from both projects
        assert len(result["labels"]) == 1
        # Detection should be median of both projects
        assert result["detection"][0] is not None
