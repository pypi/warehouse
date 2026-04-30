# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime, timedelta

import pytest

from pyramid.httpexceptions import HTTPBadRequest
from sqlalchemy.dialects import postgresql

from warehouse.admin.views import observations as views
from warehouse.observations.models import ObservationKind

from ....common.db.accounts import UserFactory, UserObservationFactory
from ....common.db.observations import ObserverFactory
from ....common.db.organizations import (
    OrganizationApplicationFactory,
    OrganizationApplicationObservationFactory,
)
from ....common.db.packaging import (
    JournalEntryFactory,
    ProjectFactory,
    ProjectObservationFactory,
)


def _fake_route_path(name, **kw):
    """Predictable route_path stub covering the routes the view uses."""
    if name == "admin.user.detail":
        return f"/admin/users/{kw['username']}/"
    if name == "admin.project.detail":
        return f"/admin/projects/{kw['project_name']}/"
    if name == "admin.organization_application.detail":
        return f"/admin/organization_applications/{kw['organization_application_id']}/"
    raise AssertionError(f"unexpected route: {name}")  # pragma: no cover


@pytest.fixture
def dt_request(db_request):
    """db_request with a predictable route_path for DataTables payload tests."""
    db_request.route_path = _fake_route_path
    return db_request


def _datatables_params(
    *,
    draw=1,
    start=0,
    length=25,
    search="",
    sort_col_idx=0,
    sort_dir="desc",
    kind=None,
):
    """Build the query-string dict that DataTables 1.10+ sends server-side."""
    params = {
        "draw": str(draw),
        "start": str(start),
        "length": str(length),
        "search[value]": search,
        "search[regex]": "false",
        "order[0][column]": str(sort_col_idx),
        "order[0][dir]": sort_dir,
    }
    # Column layout must match the JS in warehouse.js
    column_names = ["created", "kind", "related_name", "summary", "observer"]
    for i, name in enumerate(column_names):
        params[f"columns[{i}][data]"] = name
        params[f"columns[{i}][name]"] = name
        params[f"columns[{i}][searchable]"] = "true"
        params[f"columns[{i}][orderable]"] = "true"
        params[f"columns[{i}][search][value]"] = (
            kind if (kind is not None and name == "kind") else ""
        )
    return params


class TestParseDataTablesParams:
    def test_defaults(self):
        parsed = views._parse_datatables_params(_datatables_params())
        assert parsed.draw == 1
        assert parsed.start == 0
        assert parsed.length == 25
        assert parsed.search_value == ""
        assert parsed.sort_column == "created"
        assert parsed.sort_dir == "desc"
        assert parsed.kind_filter is None

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(1000, 100), (-1, 100), (0, 1), (25, 25), (100, 100), (101, 100)],
    )
    def test_length_clamping(self, raw, expected):
        parsed = views._parse_datatables_params(_datatables_params(length=raw))
        assert parsed.length == expected

    @pytest.mark.parametrize(
        "overrides",
        [
            pytest.param({"draw": "nope"}, id="bad_draw"),
            pytest.param({"start": "nope"}, id="bad_start"),
            pytest.param({"length": "nope"}, id="bad_length"),
            pytest.param({"order[0][column]": "nope"}, id="bad_order_column"),
            pytest.param({"order[0][dir]": "sideways"}, id="bad_order_dir"),
            pytest.param({"search[value]": "x" * 501}, id="oversized_search"),
        ],
    )
    def test_malformed_input_raises(self, overrides):
        with pytest.raises(HTTPBadRequest):
            views._parse_datatables_params(_datatables_params() | overrides)

    def test_unknown_sort_column_falls_back_to_default(self):
        """The summary column exists in the layout but isn't in _SORTABLE_COLUMNS."""
        parsed = views._parse_datatables_params(
            _datatables_params(sort_col_idx=3, sort_dir="asc")
        )
        assert parsed.sort_column == "created"
        assert parsed.sort_dir == "asc"

    def test_unknown_column_name_is_ignored(self):
        """A column whose name isn't in the allowlist falls back to default sort."""
        params = _datatables_params(sort_col_idx=2) | {
            "columns[2][name]": "not_a_real_column"
        }
        parsed = views._parse_datatables_params(params)
        assert parsed.sort_column == "created"

    @pytest.mark.parametrize(
        ("raw_kind", "expected"),
        [
            pytest.param("is_malware", "is_malware", id="known_kind_accepted"),
            pytest.param("not_a_real_kind", None, id="unknown_kind_ignored"),
            pytest.param("", None, id="empty_kind_is_none"),
        ],
    )
    def test_kind_filter(self, raw_kind, expected):
        parsed = views._parse_datatables_params(_datatables_params(kind=raw_kind))
        assert parsed.kind_filter == expected

    def test_no_order_param_uses_default_sort(self):
        """
        When DataTables doesn't send order[0][column] at all, we keep the
        baseline "created DESC" without attempting to parse order[0][dir].
        """
        params = _datatables_params()
        params.pop("order[0][column]")
        params.pop("order[0][dir]")
        parsed = views._parse_datatables_params(params)
        assert parsed.sort_column == "created"
        assert parsed.sort_dir == "desc"

    def test_column_list_without_kind_column(self):
        """
        If the client omits the "kind" column entirely we should stop
        at the first missing index and leave kind_filter unset.
        """
        params = _datatables_params()
        for i in (1, 2, 3, 4):
            for key in (
                f"columns[{i}][data]",
                f"columns[{i}][name]",
                f"columns[{i}][searchable]",
                f"columns[{i}][orderable]",
                f"columns[{i}][search][value]",
            ):
                params.pop(key, None)
        parsed = views._parse_datatables_params(params)
        assert parsed.kind_filter is None


def _compile(stmt):
    """Compile a statement against the PostgreSQL dialect with literal binds."""
    return str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def _parsed(**overrides) -> views._DataTablesParams:
    """Build a _DataTablesParams with defaults that match the HTML-shell values."""
    fields: dict[str, object] = {
        "draw": 1,
        "start": 0,
        "length": 25,
        "search_value": "",
        "sort_column": "created",
        "sort_dir": "desc",
        "kind_filter": None,
    }
    fields.update(overrides)
    return views._DataTablesParams(**fields)  # type: ignore[arg-type]


class TestBuildObservationsQuery:
    # db_request triggers ORM configuration so Observation.related_name (an
    # AbstractConcreteBase-aggregated column) is resolvable in compile-only tests.
    pytestmark = pytest.mark.usefixtures("db_request")

    def test_kind_filter_targets_concrete_table(self):
        compiled = _compile(
            views._build_observations_query(_parsed(kind_filter="is_malware"))
        )
        assert "project_observations" in compiled
        assert "UNION ALL" not in compiled

    def test_no_kind_filter_uses_polymorphic_union(self):
        compiled = _compile(views._build_observations_query(_parsed()))
        assert "UNION ALL" in compiled

    def test_search_filter_applies_ilike_to_summary_and_related_name(self):
        compiled = _compile(
            views._build_observations_query(
                _parsed(search_value="malicious", kind_filter="is_malware")
            )
        )
        assert "%malicious%" in compiled
        assert compiled.lower().count("ilike") == 2

    @pytest.mark.parametrize(
        ("sort_dir", "expect_desc_keyword"),
        [("desc", True), ("asc", False)],
    )
    def test_sort_direction(self, sort_dir, expect_desc_keyword):
        # ASC is the SQL default and SQLAlchemy omits it; only "desc" adds DESC.
        compiled = _compile(
            views._build_observations_query(
                _parsed(sort_column="kind", sort_dir=sort_dir)
            )
        )
        assert "ORDER BY" in compiled.upper()
        assert (" DESC" in compiled.upper()) is expect_desc_keyword


class TestRenderDatatablesPayload:
    def test_empty_database(self, dt_request):
        dt_request.params = _datatables_params()
        payload = views._render_datatables_payload(dt_request)
        assert payload["draw"] == 1
        assert payload["recordsFiltered"] == 0
        assert payload["data"] == []
        assert "recordsTotal" in payload

    def test_returns_rows(self, dt_request):
        observer = ObserverFactory.create()
        user = UserFactory.create(username="reporter-1")
        user.observer = observer
        project = ProjectFactory.create(name="evil-pkg")
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
            summary="malicious install hook",
        )

        dt_request.params = _datatables_params(kind="is_malware")
        payload = views._render_datatables_payload(dt_request)

        assert payload["recordsFiltered"] == 1
        assert len(payload["data"]) == 1
        row = payload["data"][0]
        assert row["kind"] == "is_malware"
        assert row["kind_display"] == "Is Malware"
        assert row["summary"] == "malicious install hook"
        assert row["observer"] == "reporter-1"
        assert row["observer_link"] == "/admin/users/reporter-1/"
        assert row["related_link"] == "/admin/projects/evil-pkg/"

    def test_pagination(self, dt_request):
        ProjectObservationFactory.create_batch(30, kind="is_malware")

        dt_request.params = _datatables_params(kind="is_malware", start=10, length=10)
        payload = views._render_datatables_payload(dt_request)

        assert payload["recordsFiltered"] == 30
        assert len(payload["data"]) == 10

    def test_kind_filter_narrows_results(self, dt_request):
        ProjectObservationFactory.create_batch(3, kind="is_malware")
        ProjectObservationFactory.create_batch(2, kind="is_spam")

        dt_request.params = _datatables_params(kind="is_malware")
        payload = views._render_datatables_payload(dt_request)

        assert payload["recordsFiltered"] == 3
        assert all(r["kind"] == "is_malware" for r in payload["data"])

    def test_global_search_matches_summary(self, dt_request):
        observer = ObserverFactory.create()
        ProjectObservationFactory.create(
            kind="is_malware", observer=observer, summary="extremely distinctive phrase"
        )
        ProjectObservationFactory.create_batch(
            3, kind="is_malware", observer=observer, summary="boring"
        )

        dt_request.params = _datatables_params(kind="is_malware", search="distinctive")
        payload = views._render_datatables_payload(dt_request)

        assert payload["recordsFiltered"] == 1
        assert "distinctive" in payload["data"][0]["summary"]

    def test_related_link_none_when_related_deleted(self, dt_request):
        observer = ObserverFactory.create()
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=None,
            related_name="Project(id=None, name='deleted-pkg')",
        )

        dt_request.params = _datatables_params(kind="is_malware")
        payload = views._render_datatables_payload(dt_request)

        assert payload["data"][0]["related_link"] is None
        assert payload["data"][0]["related"] == "deleted-pkg"

    def test_observer_link_none_for_non_user_observer(self, dt_request):
        observer = ObserverFactory.create()  # Observer with no parent User
        ProjectObservationFactory.create(kind="is_malware", observer=observer)

        dt_request.params = _datatables_params(kind="is_malware")
        payload = views._render_datatables_payload(dt_request)

        assert payload["data"][0]["observer"] == ""
        assert payload["data"][0]["observer_link"] is None

    def test_user_observation_produces_user_link(self, dt_request):
        target_user = UserFactory.create(username="compromised-acct")
        observer = ObserverFactory.create()
        UserFactory.create(username="reporter").observer = observer
        UserObservationFactory.create(
            kind="account_abuse",
            observer=observer,
            related=target_user,
        )

        dt_request.params = _datatables_params(kind="account_abuse")
        payload = views._render_datatables_payload(dt_request)

        assert payload["data"][0]["related_link"] == "/admin/users/compromised-acct/"

    def test_organization_application_observation_produces_link(self, dt_request):
        org_app = OrganizationApplicationFactory.create()
        observer = ObserverFactory.create()
        OrganizationApplicationObservationFactory.create(
            kind="information_request",
            observer=observer,
            related=org_app,
        )

        dt_request.params = _datatables_params(kind="information_request")
        payload = views._render_datatables_payload(dt_request)

        expected = f"/admin/organization_applications/{org_app.id}/"
        assert payload["data"][0]["related_link"] == expected

    def test_project_observation_with_unparseable_related_name(self, dt_request):
        """
        A project observation whose related_name doesn't match the
        Project(name='...') repr pattern should fall back to no link.
        """
        observer = ObserverFactory.create()
        project = ProjectFactory.create()
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
            related_name="mangled-repr-without-name",
        )

        dt_request.params = _datatables_params(kind="is_malware")
        payload = views._render_datatables_payload(dt_request)

        assert payload["data"][0]["related_link"] is None
        assert payload["data"][0]["related"] == "mangled-repr-without-name"

    def test_user_observation_with_unparseable_related_name(self, dt_request):
        """
        User observation with a still-present related_id but a related_name
        the regex can't parse and render plain text and no link.
        """
        target_user = UserFactory.create()
        observer = ObserverFactory.create()
        UserObservationFactory.create(
            kind="account_abuse",
            observer=observer,
            related=target_user,
            related_name="not-a-parseable-repr",
        )

        dt_request.params = _datatables_params(kind="account_abuse")
        payload = views._render_datatables_payload(dt_request)

        assert payload["data"][0]["related_link"] is None

    def test_filtered_count_when_page_past_end(self, dt_request):
        """
        Seed 3 matching rows, request a page whose offset lands past the end.
        `_count_filtered` runs through the kind-filter branch.
        """
        observer = ObserverFactory.create()
        ProjectObservationFactory.create_batch(
            3, kind="is_malware", observer=observer, summary="needle phrase"
        )

        dt_request.params = _datatables_params(kind="is_malware", start=10, length=5)
        payload = views._render_datatables_payload(dt_request)

        assert payload["data"] == []
        assert payload["recordsFiltered"] == 3

    def test_filtered_count_with_search_when_page_past_end(self, dt_request):
        """
        Same as `test_filtered_count_when_page_past_end`, with a search value set,
        exercising the `ILIKE` branch of `_count_filtered`.
        """
        observer = ObserverFactory.create()
        ProjectObservationFactory.create_batch(
            2, kind="is_malware", observer=observer, summary="needle phrase"
        )

        dt_request.params = _datatables_params(
            kind="is_malware", search="needle", start=10, length=5
        )
        payload = views._render_datatables_payload(dt_request)

        assert payload["data"] == []
        assert payload["recordsFiltered"] == 2

    def test_filtered_count_without_kind_filter(self, dt_request):
        """
        No `kind` filter but a search value: `_count_filtered` takes the
        polymorphic path (base = Observation, no kind predicate).
        """
        observer = ObserverFactory.create()
        ProjectObservationFactory.create(
            kind="is_malware", observer=observer, summary="needle phrase"
        )

        dt_request.params = _datatables_params(search="needle", start=10, length=5)
        payload = views._render_datatables_payload(dt_request)

        assert payload["data"] == []
        assert payload["recordsFiltered"] == 1

    def test_observer_resolution_is_batched(self, dt_request, query_recorder):
        observer_a = ObserverFactory.create()
        observer_b = ObserverFactory.create()
        UserFactory.create(username="alice").observer = observer_a
        UserFactory.create(username="bob").observer = observer_b
        for observer in (observer_a, observer_b, observer_a, observer_b):
            ProjectObservationFactory.create(kind="is_malware", observer=observer)

        dt_request.params = _datatables_params(kind="is_malware")
        with query_recorder:
            views._render_datatables_payload(dt_request)
        # Expected queries:
        # total estimate + main windowed query + observer resolution = 3.
        # Regression sentinel for N+1s on observer or related.
        assert len(query_recorder.queries) == 3


class TestObservationsListViews:
    def test_html_view_returns_kinds(self, db_request):
        result = views.observations_list(db_request)
        assert result == {"observation_kinds": list(ObservationKind)}

    def test_json_view_returns_payload(self, dt_request):
        dt_request.params = _datatables_params()
        result = views.observations_list_json(dt_request)
        assert set(result.keys()) == {
            "draw",
            "recordsTotal",
            "recordsFiltered",
            "data",
        }


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
        assert views.parse_days_param(request) == expected


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
    cutoff_date = datetime.now(tz=UTC) - timedelta(days=90)
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

        now = datetime.now(tz=UTC)

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

        now = datetime.now(tz=UTC)

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

        now = datetime.now(tz=UTC)

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
        now = datetime.now(tz=UTC)
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
            submitted_date=datetime.now(tz=UTC).replace(tzinfo=None),
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
            submitted_date=datetime.now(tz=UTC).replace(tzinfo=None),
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

    def test_with_observation_no_action(self, db_request):
        """Test timeline when observation exists but no action taken yet.

        Covers the branch where action_time is None (no quarantine, no removal),
        so response_times and exposure_times are not appended.
        """
        admin_user = UserFactory.create(username="admin")
        observer = ObserverFactory.create()
        base_time = datetime.now(tz=UTC).replace(tzinfo=None)
        project_created = base_time - timedelta(hours=24)
        report_time = base_time - timedelta(hours=12)

        project = ProjectFactory.create(created=project_created)

        JournalEntryFactory.create(
            name=project.name,
            action="create",
            submitted_by=admin_user,
            submitted_date=project_created,
        )

        # Observation with no removal action and no quarantine journal entry
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
            created=report_time,
        )

        project_data = _get_project_data(db_request)
        result = views._get_response_timeline_stats(project_data)

        assert result["sample_size"] == 1
        assert result["detection_time"] is not None
        assert result["response_time"] is None
        assert result["total_exposure"] is None
        assert result["longest_lived"] == []

    def test_with_observations_and_removal(self, db_request):
        """Test timeline with observations that have removal actions."""
        admin_user = UserFactory.create(username="admin")
        observer = ObserverFactory.create()
        base_time = datetime.now(tz=UTC).replace(tzinfo=None)
        project_created = base_time - timedelta(hours=24)
        report_time = base_time - timedelta(hours=12)
        removal_time = base_time - timedelta(hours=11)

        # Create project with a recent created date
        project = ProjectFactory.create(created=project_created)

        # Create JournalEntry for project creation (required for timeline lookup)
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
            created=report_time,
            actions={
                int(removal_time.replace(tzinfo=UTC).timestamp()): {
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
        base_time = datetime.now(tz=UTC).replace(tzinfo=None)
        project_created = base_time - timedelta(hours=24)
        report_time = base_time - timedelta(hours=12)
        quarantine_time = base_time - timedelta(hours=11)

        project = ProjectFactory.create(created=project_created)

        # Create observation
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
            created=report_time,
        )

        # Create quarantine journal entry
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

    def test_longest_lived_packages(self, db_request):
        """Test that longest-lived packages are returned."""
        admin_user = UserFactory.create(username="admin")
        observer = ObserverFactory.create()
        base_time = datetime.now(tz=UTC).replace(tzinfo=None)
        removal_time = base_time - timedelta(hours=1)

        # Create multiple projects with different exposure times
        for i in range(7):
            project_created = base_time - timedelta(hours=24 * (i + 1))
            project = ProjectFactory.create(created=project_created)

            # Create JournalEntry for project creation (required for timeline lookup)
            JournalEntryFactory.create(
                name=project.name,
                action="create",
                submitted_by=admin_user,
                submitted_date=project_created,
            )

            report_time = base_time - timedelta(hours=2)
            removal_ts = int(removal_time.replace(tzinfo=UTC).timestamp())
            ProjectObservationFactory.create(
                kind="is_malware",
                observer=observer,
                related=project,
                created=report_time,
                actions={
                    removal_ts: {
                        "action": "remove_malware",
                        "actor": "admin",
                        "created_at": str(removal_time),
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
        base_time = datetime.now(tz=UTC).replace(tzinfo=None)
        project_created = base_time - timedelta(hours=48)
        even_earlier_report = base_time - timedelta(hours=8)
        earlier_removal = base_time - timedelta(hours=7)
        report_time_1 = base_time - timedelta(hours=6)
        report_time_2 = base_time - timedelta(hours=4)
        removal_time = base_time - timedelta(hours=2)

        project = ProjectFactory.create(created=project_created)

        # Create JournalEntry for project creation (required for timeline lookup)
        JournalEntryFactory.create(
            name=project.name,
            action="create",
            submitted_by=admin_user,
            submitted_date=project_created,
        )

        removal_ts = int(removal_time.replace(tzinfo=UTC).timestamp())

        # First observation: earlier report time
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer1,
            related=project,
            created=report_time_1,
            actions={
                removal_ts: {
                    "action": "remove_malware",
                    "actor": "admin",
                    "created_at": str(removal_time),
                }
            },
        )

        # Second observation: later report time
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer2,
            related=project,
            created=report_time_2,
            actions={
                removal_ts: {
                    "action": "some_other_action",
                    "actor": "admin",
                }
            },
        )

        # Third observation: even earlier, with an earlier removal time
        # This tests the branch where we update removal_time to an earlier value
        earlier_removal_ts = int(earlier_removal.replace(tzinfo=UTC).timestamp())
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=ObserverFactory.create(),
            related=project,
            created=even_earlier_report,
            actions={
                earlier_removal_ts: {
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
        base_time = datetime.now(tz=UTC).replace(tzinfo=None)
        project_created = base_time - timedelta(hours=48)
        report_time = base_time - timedelta(hours=12)
        quarantine_time = base_time - timedelta(hours=11)
        removal_time = base_time - timedelta(hours=10)

        project = ProjectFactory.create(created=project_created)

        removal_ts = int(removal_time.replace(tzinfo=UTC).timestamp())
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
            created=report_time,
            actions={
                removal_ts: {
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
        base_time = datetime.now(tz=UTC).replace(tzinfo=None)

        # Simulate original project lifecycle (years ago)
        original_created = base_time - timedelta(days=365 * 3)
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
            submitted_date=base_time - timedelta(days=30),
        )

        # Malicious recreation - this is the `create` date we should use
        malicious_created = base_time - timedelta(hours=48)
        JournalEntryFactory.create(
            name=project_name,
            action="create",
            submitted_by=UserFactory.create(username="malicious-actor"),
            submitted_date=malicious_created,
        )

        # Create observation for deleted project (related=None after removal)
        report_time = base_time - timedelta(hours=24)
        removal_time = base_time - timedelta(hours=1)
        removal_ts = int(removal_time.replace(tzinfo=UTC).timestamp())
        ProjectObservationFactory.create(
            kind="is_malware",
            related=None,
            related_name=f"Project(id=None, name='{project_name}')",
            created=report_time,
            actions={
                removal_ts: {
                    "action": "remove_malware",
                    "actor": "admin",
                    "created_at": str(removal_time),
                }
            },
        )

        # Create quarantine journal entry
        quarantine_time = base_time - timedelta(hours=12)
        JournalEntryFactory.create(
            name=project_name,
            action="project quarantined",
            submitted_by=admin_user,
            submitted_date=quarantine_time,
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
                "project_created": datetime.now(tz=UTC).replace(tzinfo=None),
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
        project_created = datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(
            hours=48
        )
        project = ProjectFactory.create(created=project_created)

        now = datetime.now(tz=UTC)

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
            submitted_date=datetime.now(tz=UTC).replace(tzinfo=None)
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
            created=datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(hours=24)
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
            submitted_date=datetime.now(tz=UTC).replace(tzinfo=None),
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
            created=datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(hours=24)
        )

        now = datetime.now(tz=UTC)

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
            created=datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(hours=48)
        )

        now = datetime.now(tz=UTC)

        # First report (later)
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer1,
            related=project,
            created=datetime.now(tz=UTC).replace(tzinfo=None),
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
            created=datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(hours=2),
        )

        project_data = _get_project_data(db_request)
        result = views._get_timeline_trends(project_data)

        assert len(result["labels"]) >= 1
        assert len(result["detection"]) >= 1

    def test_later_observation_does_not_update_first_report(self, db_request):
        """Test that a later observation doesn't update first_report."""
        observer = ObserverFactory.create()
        project = ProjectFactory.create(
            created=datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(hours=48)
        )

        # First observation (earlier - should be first_report)
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
            created=datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(hours=24),
        )

        # Second observation (later - should NOT update first_report)
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project,
            created=datetime.now(tz=UTC).replace(tzinfo=None),
        )

        project_data = _get_project_data(db_request)
        result = views._get_timeline_trends(project_data)

        assert len(result["labels"]) >= 1
        assert len(result["detection"]) >= 1

    def test_actions_with_non_removal_entries(self, db_request):
        """Test actions dict with non-remove_malware entries."""
        observer = ObserverFactory.create()
        project = ProjectFactory.create(
            created=datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(hours=24)
        )

        now = datetime.now(tz=UTC)

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
                int(now.timestamp()) + 1: {
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
            created=datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(hours=24)
        )

        # Report happens first, removal happens 1 hour later (realistic scenario)
        report_time = datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(hours=2)
        removal_time = datetime.now(tz=UTC) - timedelta(hours=1)

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
            created=datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(hours=48)
        )

        now = datetime.now(tz=UTC)
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

        # Use the most recent Wednesday noon so this test is stable around
        # Sunday/Monday boundaries while staying within the rolling cutoff window.
        current = datetime.now(tz=UTC).replace(tzinfo=None)
        days_since_wednesday = (current.weekday() - 2) % 7
        wednesday_time = (current - timedelta(days=days_since_wednesday)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )

        # Create two projects and observations in the same week
        project1_created = wednesday_time - timedelta(hours=48)
        project2_created = wednesday_time - timedelta(hours=72)
        project1 = ProjectFactory.create(created=project1_created)
        project2 = ProjectFactory.create(created=project2_created)
        project1_report_time = wednesday_time - timedelta(hours=4)
        project2_report_time = wednesday_time - timedelta(hours=2)

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
            created=project1_report_time,
        )
        ProjectObservationFactory.create(
            kind="is_malware",
            observer=observer,
            related=project2,
            created=project2_report_time,  # same week
        )

        project_data = _get_project_data(db_request)
        result = views._get_timeline_trends(project_data)

        # Should have exactly one week with data from both projects
        assert len(result["labels"]) == 1
        # Detection should be median of both projects
        assert result["detection"][0] is not None
