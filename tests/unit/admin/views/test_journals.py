# SPDX-License-Identifier: Apache-2.0

import datetime

import pytest

from pyramid.httpexceptions import HTTPBadRequest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from warehouse.admin.views import journals as views

from ....common.db.accounts import UserFactory
from ....common.db.packaging import JournalEntryFactory


def _tabulator_params(*, page=None, size=None, sort=None, filters=None):
    """Build the query-string dict Tabulator sends in remote mode."""
    params = {}
    if page is not None:
        params["page"] = str(page)
    if size is not None:
        params["size"] = str(size)
    if sort is not None:
        params["sort[0][field]"] = sort[0]
        params["sort[0][dir]"] = sort[1]
    for i, (field, value) in enumerate((filters or {}).items()):
        params[f"filter[{i}][field]"] = field
        params[f"filter[{i}][type]"] = "like"
        params[f"filter[{i}][value]"] = value
    return params


def _ids_newest_first(journals):
    """IDs in the view's default order: submitted_date desc, id tiebreak."""
    return [
        j.id
        for j in sorted(journals, key=lambda j: (j.submitted_date, j.id), reverse=True)
    ]


class TestParseTabulatorParams:
    def test_defaults(self):
        parsed = views._parse_tabulator_params({})
        assert parsed.page == 1
        assert parsed.size == 25
        assert parsed.sort_field == "submitted_date"
        assert parsed.sort_dir == "desc"
        assert parsed.filters == {}

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(-5, 1), (0, 1), (25, 25), (100, 100), (1000, 100)],
    )
    def test_size_clamping(self, raw, expected):
        parsed = views._parse_tabulator_params(_tabulator_params(size=raw))
        assert parsed.size == expected

    def test_page_clamped_to_one(self):
        parsed = views._parse_tabulator_params(_tabulator_params(page=-3))
        assert parsed.page == 1

    @pytest.mark.parametrize(
        "overrides",
        [
            pytest.param({"page": "nope"}, id="bad_page"),
            pytest.param({"size": "nope"}, id="bad_size"),
            pytest.param({"page": "999999"}, id="page_too_deep"),
            pytest.param(
                {"sort[0][field]": "name", "sort[0][dir]": "sideways"},
                id="bad_sort_dir",
            ),
            pytest.param(
                {"filter[0][field]": "name", "filter[0][value]": "x" * 501},
                id="oversized_filter",
            ),
        ],
    )
    def test_malformed_input_raises(self, overrides):
        with pytest.raises(HTTPBadRequest):
            views._parse_tabulator_params(_tabulator_params() | overrides)

    def test_sort_params(self):
        parsed = views._parse_tabulator_params(_tabulator_params(sort=("name", "asc")))
        assert parsed.sort_field == "name"
        assert parsed.sort_dir == "asc"

    @pytest.mark.parametrize("field", ["action", "version", "nonsense"])
    def test_unsortable_field_falls_back_to_default(self, field):
        parsed = views._parse_tabulator_params(_tabulator_params(sort=(field, "asc")))
        assert parsed.sort_field == "submitted_date"
        assert parsed.sort_dir == "desc"

    def test_filters(self):
        parsed = views._parse_tabulator_params(
            _tabulator_params(
                filters={
                    "name": "pip",
                    "submitted_by": "someuser",
                    "nonsense": "ignored",
                    "action": "   ",
                }
            )
        )
        assert parsed.filters == {"name": "pip", "submitted_by": "someuser"}


class TestBuildJournalsQuery:
    @pytest.mark.parametrize(
        ("sort", "expected_order"),
        [
            (
                ("submitted_date", "desc"),
                "journals.submitted_date DESC, journals.id DESC",
            ),
            (
                ("submitted_date", "asc"),
                "journals.submitted_date ASC, journals.id ASC",
            ),
            (("name", "desc"), "journals.name DESC, journals.id ASC"),
            (("name", "asc"), "journals.name ASC, journals.id DESC"),
            (
                ("submitted_by", "desc"),
                "journals.submitted_by DESC,"
                " journals.submitted_date ASC, journals.id ASC",
            ),
            (
                ("submitted_by", "asc"),
                "journals.submitted_by ASC,"
                " journals.submitted_date DESC, journals.id DESC",
            ),
        ],
    )
    def test_order_matches_index_orientation(self, sort, expected_order):
        """Each sort orders exactly as an index stores it, tiebreaks included."""
        params = views._parse_tabulator_params(_tabulator_params(sort=sort))
        sql = str(
            views._build_journals_query(params).compile(dialect=postgresql.dialect())
        )
        assert expected_order in sql
        # Native NULL ordering only; forcing NULLS LAST onto a DESC sort
        # would defeat the btree indexes.
        assert "NULLS" not in sql

    def test_name_filtered_chronological_sort_orders_by_id(self):
        """An exact name filter swaps the date sort for the equivalent id
        order, so journals_name_id_idx can serve the query natively."""
        params = views._parse_tabulator_params(
            _tabulator_params(filters={"name": "pip"})
        )
        sql = str(
            views._build_journals_query(params).compile(dialect=postgresql.dialect())
        )
        assert "ORDER BY journals.id DESC" in sql
        assert "submitted_date DESC" not in sql

    def test_fetches_one_extra_row(self):
        params = views._parse_tabulator_params(_tabulator_params(page=2, size=10))
        sql = str(
            views._build_journals_query(params).compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert "LIMIT 11" in sql
        assert "OFFSET 10" in sql


class TestRenderTabulatorPayload:
    def test_empty_database(self, route_request):
        assert views._render_tabulator_payload(route_request) == {
            "last_page": 1,
            "total": 0,
            "total_estimate": None,
            "data": [],
        }

    def test_returns_rows_most_recent_first(self, route_request):
        journals = JournalEntryFactory.create_batch(30)
        expected_ids = _ids_newest_first(journals)

        result = views._render_tabulator_payload(route_request)

        assert result["last_page"] == 2
        assert [row["id"] for row in result["data"]] == expected_ids[:25]

    def test_row_shape(self, route_request):
        user = UserFactory.create()
        journal = JournalEntryFactory.create(action="create", submitted_by=user)

        result = views._render_tabulator_payload(route_request)

        assert result["data"] == [
            {
                "id": journal.id,
                "name": journal.name,
                "version": journal.version,
                "action": "create",
                "submitted_date": journal.submitted_date.isoformat(),
                "submitted_by": user.username,
                "project_link": f"/admin/projects/{journal.name}/",
                "submitted_by_link": f"/admin/users/{user.username}/",
            }
        ]

    def test_links_none_without_name_or_user(self, route_request):
        JournalEntryFactory.create(name=None, submitted_by=None)

        result = views._render_tabulator_payload(route_request)

        row = result["data"][0]
        assert row["project_link"] is None
        assert row["submitted_by"] is None
        assert row["submitted_by_link"] is None

    def test_second_page(self, route_request):
        journals = JournalEntryFactory.create_batch(30)
        expected_ids = _ids_newest_first(journals)
        route_request.GET.update(_tabulator_params(page=2))

        result = views._render_tabulator_payload(route_request)

        assert result["last_page"] == 2
        assert [row["id"] for row in result["data"]] == expected_ids[25:]
        # The final page is in reach, so the exact total is known.
        assert result["total"] == 30

    def test_exact_page_boundary_has_no_next_page(self, route_request):
        JournalEntryFactory.create_batch(25)

        result = views._render_tabulator_payload(route_request)

        assert result["last_page"] == 1
        assert len(result["data"]) == 25
        assert result["total"] == 25

    def test_filtered_pagination_is_rolling(self, route_request):
        """With filters active there is no count, only a next-page probe."""
        JournalEntryFactory.create_batch(3, name="pip")

        route_request.GET.update(_tabulator_params(size=2, filters={"name": "pip"}))
        result = views._render_tabulator_payload(route_request)

        assert len(result["data"]) == 2
        assert result["last_page"] == 2
        # More filtered pages exist, so no total can be reported.
        assert result["total"] is None
        assert result["total_estimate"] is None

    def test_filtered_final_page_reports_exact_total(self, route_request):
        """A short filtered page pins the exact total without a count query."""
        JournalEntryFactory.create_batch(3, name="pip")
        JournalEntryFactory.create(name="numpy")

        route_request.GET.update(_tabulator_params(filters={"name": "pip"}))
        result = views._render_tabulator_payload(route_request)

        assert result["total"] == 3
        assert result["total_estimate"] is None

    def test_unfiltered_last_page_uses_estimate(self, route_request):
        """Unfiltered, the pg_class row estimate sizes the pagination."""
        JournalEntryFactory.create_batch(10)
        route_request.db.execute(text("ANALYZE journals"))

        route_request.GET.update(_tabulator_params(size=2))
        result = views._render_tabulator_payload(route_request)

        assert len(result["data"]) == 2
        assert result["last_page"] == 5
        assert result["total"] is None
        assert result["total_estimate"] == 10

    def test_stale_estimate_clamped_to_rows_fetched(self, route_request, monkeypatch):
        """A stale table estimate never undercounts rows already fetched."""
        monkeypatch.setattr(views, "estimate_row_count", lambda *a: 0)
        JournalEntryFactory.create_batch(3)

        route_request.GET.update(_tabulator_params(size=2))
        result = views._render_tabulator_payload(route_request)

        assert result["total_estimate"] == 3
        assert result["last_page"] == 2

    def test_last_page_capped_at_max_offset(self, route_request, monkeypatch):
        monkeypatch.setattr(views, "_MAX_OFFSET", 4)
        JournalEntryFactory.create_batch(5)
        route_request.GET.update(_tabulator_params(page=2, size=2))

        result = views._render_tabulator_payload(route_request)

        assert len(result["data"]) == 2
        assert result["last_page"] == 2

    def test_name_filter_is_exact(self, route_request):
        journal = JournalEntryFactory.create(name="Django")
        JournalEntryFactory.create(name="Django-extras")

        route_request.GET.update(_tabulator_params(filters={"name": "Django"}))
        result = views._render_tabulator_payload(route_request)
        assert [row["id"] for row in result["data"]] == [journal.id]

        # Exact name matches are case-sensitive.
        route_request.GET.update(_tabulator_params(filters={"name": "django"}))
        result = views._render_tabulator_payload(route_request)
        assert result["data"] == []

    def test_version_filter_is_exact(self, route_request):
        journal = JournalEntryFactory.create(version="1.0")
        JournalEntryFactory.create(version="1.0.1")

        route_request.GET.update(_tabulator_params(filters={"version": "1.0"}))
        result = views._render_tabulator_payload(route_request)

        assert [row["id"] for row in result["data"]] == [journal.id]

    def test_submitted_by_filter_is_case_insensitive(self, route_request):
        user = UserFactory.create(username="journaluser")
        journal = JournalEntryFactory.create(submitted_by=user)
        JournalEntryFactory.create()

        route_request.GET.update(
            _tabulator_params(filters={"submitted_by": "JournalUser"})
        )
        result = views._render_tabulator_payload(route_request)

        assert [row["id"] for row in result["data"]] == [journal.id]

    def test_action_filter_is_a_prefix_match(self, route_request):
        matching = JournalEntryFactory.create(action="add Owner someuser")
        JournalEntryFactory.create(action="remove Owner someuser")

        route_request.GET.update(_tabulator_params(filters={"action": "add Owner"}))
        result = views._render_tabulator_payload(route_request)

        assert [row["id"] for row in result["data"]] == [matching.id]

    def test_action_filter_escapes_like_wildcards(self, route_request):
        matching = JournalEntryFactory.create(action="add% literally")
        JournalEntryFactory.create(action="add Owner someuser")

        route_request.GET.update(_tabulator_params(filters={"action": "add%"}))
        result = views._render_tabulator_payload(route_request)

        assert [row["id"] for row in result["data"]] == [matching.id]

    def test_multiple_filters_combine_with_and(self, route_request):
        user = UserFactory.create(username="someuser")
        matching = JournalEntryFactory.create(name="pip", submitted_by=user)
        JournalEntryFactory.create(name="pip")
        JournalEntryFactory.create(submitted_by=user)

        route_request.GET.update(
            _tabulator_params(filters={"name": "pip", "submitted_by": "someuser"})
        )
        result = views._render_tabulator_payload(route_request)

        assert [row["id"] for row in result["data"]] == [matching.id]

    def test_submitted_date_filter_includes_whole_day(self, route_request):
        on_day = JournalEntryFactory.create(
            submitted_date=datetime.datetime(2023, 1, 15, 23, 59)
        )
        before = JournalEntryFactory.create(
            submitted_date=datetime.datetime(2023, 1, 10, 8, 0)
        )
        JournalEntryFactory.create(submitted_date=datetime.datetime(2023, 1, 16, 0, 0))

        route_request.GET.update(
            _tabulator_params(filters={"submitted_date": "2023-01-15"})
        )
        result = views._render_tabulator_payload(route_request)

        assert [row["id"] for row in result["data"]] == [on_day.id, before.id]

    def test_submitted_date_filter_with_datetime(self, route_request):
        at_noon = JournalEntryFactory.create(
            submitted_date=datetime.datetime(2023, 1, 15, 12, 0)
        )
        JournalEntryFactory.create(submitted_date=datetime.datetime(2023, 1, 15, 12, 1))

        route_request.GET.update(
            _tabulator_params(filters={"submitted_date": "2023-01-15T12:00:00"})
        )
        result = views._render_tabulator_payload(route_request)

        assert [row["id"] for row in result["data"]] == [at_noon.id]

    def test_submitted_date_filter_invalid(self, route_request):
        route_request.GET.update(
            _tabulator_params(filters={"submitted_date": "yesterday"})
        )
        with pytest.raises(HTTPBadRequest):
            views._render_tabulator_payload(route_request)

    def test_desc_sort_places_nulls_first(self, route_request):
        """Native NULL ordering (first on DESC) keeps the sort on the index."""
        second = JournalEntryFactory.create(
            submitted_by=UserFactory.create(username="aaa")
        )
        first = JournalEntryFactory.create(
            submitted_by=UserFactory.create(username="bbb")
        )
        unattributed = JournalEntryFactory.create(submitted_by=None)

        route_request.GET.update(_tabulator_params(sort=("submitted_by", "desc")))
        result = views._render_tabulator_payload(route_request)

        assert [row["id"] for row in result["data"]] == [
            unattributed.id,
            first.id,
            second.id,
        ]

    def test_last_page_matches_deepest_valid_page(self, route_request, monkeypatch):
        """last_page never advertises a page the parser would reject."""
        monkeypatch.setattr(views, "_MAX_OFFSET", 10)
        JournalEntryFactory.create_batch(13, name="pip")

        # Page 4 with size 3 is the deepest valid page (offset 9 < 10).
        route_request.GET.update(
            _tabulator_params(page=4, size=3, filters={"name": "pip"})
        )
        result = views._render_tabulator_payload(route_request)
        assert len(result["data"]) == 3
        assert result["last_page"] == 4

        # ...and page 5 is exactly where the parser draws the line.
        with pytest.raises(HTTPBadRequest):
            views._parse_tabulator_params(_tabulator_params(page=5, size=3))

    def test_sort_by_name_ascending(self, route_request):
        journals = [
            JournalEntryFactory.create(name=name) for name in ["beta", "alpha", "zeta"]
        ]

        route_request.GET.update(_tabulator_params(sort=("name", "asc")))
        result = views._render_tabulator_payload(route_request)

        expected_ids = [j.id for j in sorted(journals, key=lambda j: (j.name, j.id))]
        assert [row["id"] for row in result["data"]] == expected_ids


class TestJournalsListViews:
    def test_html_view_returns_empty_context(self, db_request):
        assert views.journals_list(db_request) == {}

    def test_json_view_returns_payload(self, route_request):
        journal = JournalEntryFactory.create()

        result = views.journals_list_json(route_request)

        assert result["last_page"] == 1
        assert [row["id"] for row in result["data"]] == [journal.id]
