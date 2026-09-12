# SPDX-License-Identifier: Apache-2.0

"""Admin views for Journal Entries.

The journals table is one of the largest in the database (hundreds of
millions of rows), so these views deliberately avoid whole-table counts
and unbounded scans. The list page is a Tabulator table fed by a JSON
endpoint speaking Tabulator's remote pagination/sort/filter protocol.

See: https://github.com/pypi/warehouse/issues/14541
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from pyramid.httpexceptions import HTTPBadRequest
from pyramid.view import view_config
from sqlalchemy import select

from warehouse.admin.views.helpers import (
    TABULATOR_STATEMENT_TIMEOUT_MS,
    TabulatorParams,
    execute_bounded,
    parse_tabulator_params,
    tabulator_page,
)
from warehouse.authnz import Permissions
from warehouse.cache.http import add_vary
from warehouse.packaging.models import JournalEntry

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from pyramid.request import Request
    from sqlalchemy import Select
    from sqlalchemy.sql import ColumnElement


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


def _build_order_by(params: TabulatorParams) -> tuple[ColumnElement[Any], ...]:
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


def _build_journals_query(params: TabulatorParams) -> Select[Any]:
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
    params = parse_tabulator_params(
        request.params,
        sortable_fields=_SORTABLE_FIELDS,
        default_sort_field="submitted_date",
        filter_fields=_FILTER_BUILDERS,
    )
    rows = execute_bounded(
        request,
        _build_journals_query(params),
        timeout_ms=TABULATOR_STATEMENT_TIMEOUT_MS,
    )
    page_rows, pagination = tabulator_page(
        request, rows, params, table_names=[JournalEntry.__tablename__]
    )

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

    return {**pagination, "data": data}


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
