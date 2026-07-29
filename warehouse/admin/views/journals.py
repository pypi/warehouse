# SPDX-License-Identifier: Apache-2.0

"""Admin views for Journal Entries.

The journals table is one of the largest in the database (hundreds of
millions of rows), so these views deliberately avoid whole-table counts
and unbounded scans. The list page is a Tabulator table fed by a JSON
endpoint speaking Tabulator's remote pagination/sort/filter protocol.

See: https://github.com/pypi/warehouse/issues/14541
"""

from __future__ import annotations

import math

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from pyramid.httpexceptions import HTTPBadRequest
from pyramid.view import view_config
from sqlalchemy import select

from warehouse.admin.views.helpers import estimate_row_count, execute_bounded
from warehouse.authnz import Permissions
from warehouse.cache.http import add_vary
from warehouse.packaging.models import JournalEntry

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from typing import Any

    from pyramid.request import Request
    from sqlalchemy import Select
    from sqlalchemy.sql import ColumnElement

_DEFAULT_PAGE_SIZE = 25
_MAX_PAGE_SIZE = 100
# Deepest row reachable via pagination; keeps OFFSET scans bounded.
# Anything further back should be reached by filtering instead.
_MAX_OFFSET = 10_000
_MAX_FILTER_LENGTH = 500
# Backstop for filter/sort combinations the indexes cannot serve, e.g. an
# action prefix that matches nothing. Timed-out queries become a 400.
_STATEMENT_TIMEOUT_MS = 10_000


def _submitted_on_or_before(value: str) -> ColumnElement[bool]:
    """Match journal entries submitted on or before an ISO date/datetime.

    Paired with the default newest-first sort, this jumps to any point in
    history without deep OFFSETs, using the submitted_date index.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise HTTPBadRequest(
            "'submitted_date' filter must be an ISO date, e.g. 2023-01-31."
        ) from None
    if len(value) == 10:  # date-only: include the whole day
        return JournalEntry.submitted_date < parsed + timedelta(days=1)
    return JournalEntry.submitted_date <= parsed


# Exact matches use the existing btree indexes on the journals table.
# `submitted_by` is CITEXT, so equality is case-insensitive. `action` has
# no index, so a prefix match is best-effort: ordered scans find common
# actions quickly, and the statement timeout bounds the rare ones.
_FILTER_BUILDERS: dict[str, Callable[[str], ColumnElement[bool]]] = {
    "name": lambda v: JournalEntry.name == v,
    "version": lambda v: JournalEntry.version == v,
    "submitted_by": lambda v: JournalEntry._submitted_by == v,
    "action": lambda v: JournalEntry.action.startswith(v, autoescape=True),
    "submitted_date": _submitted_on_or_before,
}

# Sortable columns are backed by an index; `action` is not, and `version`
# is text, where a lexicographic order would only mislead.
_SORTABLE_FIELDS = frozenset({"submitted_date", "name", "submitted_by"})


@dataclass(frozen=True)
class _TabulatorParams:
    page: int
    size: int
    sort_field: str
    sort_dir: str
    filters: dict[str, str]

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


def _parse_tabulator_params(params: Mapping[str, str]) -> _TabulatorParams:
    """Parse and validate Tabulator's remote ajax query params."""
    try:
        page = max(1, int(params.get("page", "1")))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    try:
        raw_size = int(params.get("size", str(_DEFAULT_PAGE_SIZE)))
    except ValueError:
        raise HTTPBadRequest("'size' must be an integer.") from None
    size = min(max(1, raw_size), _MAX_PAGE_SIZE)

    sort_field = "submitted_date"
    sort_dir = "desc"
    requested_field = params.get("sort[0][field]")
    if requested_field is not None:
        requested_dir = params.get("sort[0][dir]", "desc")
        if requested_dir not in ("asc", "desc"):
            raise HTTPBadRequest("'sort[0][dir]' must be 'asc' or 'desc'.")
        if requested_field in _SORTABLE_FIELDS:
            sort_field = requested_field
            sort_dir = requested_dir

    filters: dict[str, str] = {}
    i = 0
    while (field := params.get(f"filter[{i}][field]")) is not None:
        value = (params.get(f"filter[{i}][value]") or "").strip()
        if len(value) > _MAX_FILTER_LENGTH:
            raise HTTPBadRequest(
                f"Filter values must be <= {_MAX_FILTER_LENGTH} characters."
            )
        if value and field in _FILTER_BUILDERS:
            filters[field] = value
        i += 1

    parsed = _TabulatorParams(
        page=page, size=size, sort_field=sort_field, sort_dir=sort_dir, filters=filters
    )
    if parsed.offset >= _MAX_OFFSET:
        raise HTTPBadRequest(f"Cannot paginate beyond {_MAX_OFFSET} rows.")
    return parsed


def _build_order_by(params: _TabulatorParams) -> tuple[ColumnElement[Any], ...]:
    """Choose an ordering the indexes can serve without a sort step.

    Plain asc/desc keeps PostgreSQL's native NULL placement (last on ASC,
    first on DESC), which is what the btree indexes store, and each
    tiebreak follows its index's stored orientation — a same-direction
    tiebreak would force a sort over every row of the first sort-key group.
    """
    desc = params.sort_dir == "desc"
    if params.sort_field == "name":
        # journals_name_id_idx stores (name ASC, id DESC).
        if desc:
            return (JournalEntry.name.desc(), JournalEntry.id.asc())
        return (JournalEntry.name.asc(), JournalEntry.id.desc())
    if params.sort_field == "submitted_by":
        # journals_submitted_by_and_reverse_date_idx stores
        # (submitted_by ASC, submitted_date DESC).
        if desc:
            return (
                JournalEntry._submitted_by.desc(),
                JournalEntry.submitted_date.asc(),
                JournalEntry.id.asc(),
            )
        return (
            JournalEntry._submitted_by.asc(),
            JournalEntry.submitted_date.desc(),
            JournalEntry.id.desc(),
        )
    if "name" in params.filters:
        # Chronological sort with an exact name filter: id order is
        # equivalent (ids are kept monotonic, see ensure_monotonic_journals)
        # and journals_name_id_idx serves it without scanning other
        # projects' rows out of the date index.
        return (JournalEntry.id.desc() if desc else JournalEntry.id.asc(),)
    # journals_submitted_date_id_idx stores (submitted_date ASC, id ASC).
    if desc:
        return (JournalEntry.submitted_date.desc(), JournalEntry.id.desc())
    return (JournalEntry.submitted_date.asc(), JournalEntry.id.asc())


def _build_journals_query(params: _TabulatorParams) -> Select[Any]:
    """Build the page SELECT, fetching one extra row to detect a next page."""
    conditions = [
        _FILTER_BUILDERS[field](value) for field, value in params.filters.items()
    ]

    return (
        select(
            JournalEntry.id,
            JournalEntry.name,
            JournalEntry.version,
            JournalEntry.action,
            JournalEntry.submitted_date,
            JournalEntry._submitted_by.label("submitted_by"),
        )
        .where(*conditions)
        .order_by(*_build_order_by(params))
        .limit(params.size + 1)
        .offset(params.offset)
    )


def _render_tabulator_payload(request: Request) -> dict[str, Any]:
    """Execute the page query and shape Tabulator's expected response."""
    params = _parse_tabulator_params(request.params)
    rows = execute_bounded(
        request, _build_journals_query(params), timeout_ms=_STATEMENT_TIMEOUT_MS
    )

    # The deepest page the parser will accept for this size.
    max_page = math.ceil(_MAX_OFFSET / params.size)
    has_more = len(rows) > params.size
    page_rows = rows[: params.size]
    total: int | None = None
    total_estimate: int | None = None
    if not has_more:
        # The final page is in reach, so the exact total is known without
        # a count query: everything skipped plus everything returned.
        last_page = params.page
        total = params.offset + len(page_rows)
    elif params.filters:
        # Counting filtered matches is unbounded work on this table, so
        # filtered pagination only advertises one page past the current one.
        last_page = min(params.page + 1, max_page)
    else:
        # Unfiltered, the pg_class row estimate is accurate enough to size
        # the pagination controls, bounded by the offset cap. Clamp to the
        # rows already fetched (probe row included, so a next page is
        # always advertised) in case the estimate is stale.
        total_estimate = max(
            estimate_row_count(request, [JournalEntry.__tablename__]),
            params.offset + len(rows),
        )
        last_page = min(math.ceil(total_estimate / params.size), max_page)

    # Project-scoped pages repeat the same name on every row; generate each
    # distinct link once.
    project_links = {
        name: request.route_path("admin.project.detail", project_name=name)
        for name in {row.name for row in page_rows} - {None}
    }
    user_links = {
        username: request.route_path("admin.user.detail", username=username)
        for username in {row.submitted_by for row in page_rows} - {None}
    }
    data = [
        {
            "id": row.id,
            "name": row.name,
            "version": row.version,
            "action": row.action,
            "submitted_date": row.submitted_date.isoformat(),
            "submitted_by": row.submitted_by,
            "project_link": project_links.get(row.name),
            "submitted_by_link": user_links.get(row.submitted_by),
        }
        for row in page_rows
    ]

    # `total` is exact when set; `total_estimate` is the table estimate for
    # unfiltered browsing. Both are null when more filtered pages exist.
    return {
        "last_page": last_page,
        "total": total,
        "total_estimate": total_estimate,
        "data": data,
    }


@view_config(
    route_name="admin.journals.list",
    renderer="warehouse.admin:templates/admin/journals/list.html",
    accept="text/html",
    decorator=[add_vary("Accept")],
    permission=Permissions.AdminJournalRead,
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def journals_list(request: Request) -> dict[str, Any]:
    return {}


@view_config(
    route_name="admin.journals.list",
    renderer="json",
    accept="application/json",
    decorator=[add_vary("Accept")],
    permission=Permissions.AdminJournalRead,
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def journals_list_json(request: Request) -> dict[str, Any]:
    return _render_tabulator_payload(request)
