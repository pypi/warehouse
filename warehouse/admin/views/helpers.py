# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import math

from dataclasses import dataclass
from typing import TYPE_CHECKING

from psycopg.errors import QueryCanceled
from pyramid.httpexceptions import HTTPBadRequest
from sqlalchemy import func, select, text

if TYPE_CHECKING:
    from collections.abc import Container, Iterable, Mapping, Sequence
    from typing import Any

    from pyramid.request import Request
    from sqlalchemy import Row, Select

# Valid time periods for filtering
ALLOWED_DAYS = (30, 60, 90)
DEFAULT_DAYS = 30

# Defaults for the admin's remote-mode Tabulator tables. These sit on tables
# too large to COUNT(*), so pagination is deliberately bounded: OFFSET scans
# stop at _MAX_OFFSET and every page query runs under a statement timeout.
TABULATOR_DEFAULT_PAGE_SIZE = 25
TABULATOR_MAX_PAGE_SIZE = 100
TABULATOR_MAX_OFFSET = 10_000
TABULATOR_MAX_FILTER_LENGTH = 500
TABULATOR_STATEMENT_TIMEOUT_MS = 10_000


def parse_days_param(request: Request, allowed: tuple[int, ...] = ALLOWED_DAYS) -> int:
    """Parse and validate the 'days' query parameter."""
    try:
        days = int(request.params.get("days", DEFAULT_DAYS))
        return days if days in allowed else DEFAULT_DAYS
    except ValueError, TypeError:
        return DEFAULT_DAYS


def estimate_row_count(request: Request, table_names: Iterable[str]) -> int:
    """Estimate total rows across tables via pg_class.reltuples — sub-millisecond.

    reltuples is -1 for never-analyzed tables, so each table's estimate is
    clamped to zero. Only relations in the public schema are considered, so
    a same-named table in another schema cannot skew the estimate.

    For exact, periodically-refreshed counts of a few core tables, see
    warehouse.utils.row_counter instead; this helper is for tables too
    large to COUNT(*).
    """
    result = request.db.execute(
        text(
            "SELECT COALESCE(SUM(GREATEST(reltuples, 0))::bigint, 0) FROM pg_class "
            "WHERE relname = ANY(:names) AND relkind = 'r' "
            "AND relnamespace = 'public'::regnamespace"
        ),
        {"names": list(table_names)},
    ).scalar()
    return int(result)


def execute_bounded(
    request: Request, stmt: Select[Any], *, timeout_ms: int
) -> Sequence[Row[Any]]:
    """Run a query under a statement timeout, turning timeouts into a 400.

    A query the indexes cannot serve would otherwise scan until the
    connection drops. The timeout stays in force for the remainder of the
    transaction, so any later statements in the same request run under it
    too (only cancellations raised *here* become a 400). Other database
    errors — connection drops, deadlocks — surface as server errors.

    The raw psycopg exception is caught because warehouse.db unwraps
    SQLAlchemy's DBAPIError back to the driver exception engine-wide.
    """
    try:
        # set_config(..., is_local=true) scopes the timeout to this
        # transaction, so it does not leak to the pooled connection.
        request.db.execute(
            select(func.set_config("statement_timeout", str(timeout_ms), True))
        )
        return request.db.execute(stmt).all()
    except QueryCanceled:
        raise HTTPBadRequest(
            "Query took too long; narrow your filters and try again."
        ) from None


@dataclass(frozen=True)
class TabulatorParams:
    """One page request from a Tabulator table in remote mode."""

    page: int
    size: int
    sort_field: str
    sort_dir: str
    filters: dict[str, str]

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


def parse_tabulator_params(
    params: Mapping[str, str],
    *,
    sortable_fields: Container[str],
    default_sort_field: str,
    filter_fields: Container[str],
    default_sort_dir: str = "desc",
) -> TabulatorParams:
    """Parse and validate Tabulator's remote ajax query params.

    A sort on a field outside `sortable_fields` falls back to the default
    rather than erroring, since Tabulator will happily ask to sort by any
    column: views list only the fields an index can serve. Filters on fields
    outside `filter_fields` are dropped for the same reason. Values are
    returned as sent — a view wanting to validate one against an enum does so
    where it builds the query.
    """
    try:
        page = max(1, int(params.get("page", "1")))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    try:
        raw_size = int(params.get("size", str(TABULATOR_DEFAULT_PAGE_SIZE)))
    except ValueError:
        raise HTTPBadRequest("'size' must be an integer.") from None
    size = min(max(1, raw_size), TABULATOR_MAX_PAGE_SIZE)

    sort_field = default_sort_field
    sort_dir = default_sort_dir
    requested_field = params.get("sort[0][field]")
    if requested_field is not None:
        requested_dir = params.get("sort[0][dir]", default_sort_dir)
        if requested_dir not in ("asc", "desc"):
            raise HTTPBadRequest("'sort[0][dir]' must be 'asc' or 'desc'.")
        if requested_field in sortable_fields:
            sort_field = requested_field
            sort_dir = requested_dir

    filters: dict[str, str] = {}
    i = 0
    while (field := params.get(f"filter[{i}][field]")) is not None:
        value = (params.get(f"filter[{i}][value]") or "").strip()
        if len(value) > TABULATOR_MAX_FILTER_LENGTH:
            raise HTTPBadRequest(
                f"Filter values must be <= {TABULATOR_MAX_FILTER_LENGTH} characters."
            )
        if value and field in filter_fields:
            filters[field] = value
        i += 1

    parsed = TabulatorParams(
        page=page, size=size, sort_field=sort_field, sort_dir=sort_dir, filters=filters
    )
    if parsed.offset >= TABULATOR_MAX_OFFSET:
        raise HTTPBadRequest(f"Cannot paginate beyond {TABULATOR_MAX_OFFSET} rows.")
    return parsed


def tabulator_page(
    request: Request,
    rows: Sequence[Row[Any]],
    params: TabulatorParams,
    *,
    table_names: Iterable[str],
) -> tuple[Sequence[Row[Any]], dict[str, Any]]:
    """Split off the probe row and size the pagination controls.

    Expects `rows` to hold up to `size + 1` rows — the extra one is how a next
    page is detected without counting. Returns the rows to render and the
    envelope to merge with the view's own `data`, where `total` is exact when
    set and `total_estimate` is the whole-table estimate for unfiltered
    browsing. Both are null part-way through a filtered result, where counting
    the matches is the unbounded work these endpoints exist to avoid.
    """
    # The deepest page the parser will accept for this size.
    max_page = math.ceil(TABULATOR_MAX_OFFSET / params.size)
    has_more = len(rows) > params.size
    page_rows = rows[: params.size]
    total: int | None = None
    total_estimate: int | None = None

    if not page_rows and params.offset:
        # The rows ran out before this page even started. Everything skipped
        # is an offset, not a count of rows that exist, so claiming it as the
        # total would invent them; the real total is only known to be at most
        # that, and finding it exactly is the count these endpoints avoid.
        last_page = params.page
    elif not has_more:
        # The final page is in reach, so the exact total is known without a
        # count query: everything skipped plus everything returned.
        last_page = params.page
        total = params.offset + len(page_rows)
    elif params.filters:
        # Counting filtered matches is unbounded work, so filtered pagination
        # only advertises one page past the current one.
        last_page = min(params.page + 1, max_page)
    else:
        # Unfiltered, the pg_class row estimate is accurate enough to size the
        # pagination controls, bounded by the offset cap. Clamp to the rows
        # already fetched (probe row included, so a next page is always
        # advertised) in case the estimate is stale.
        total_estimate = max(
            estimate_row_count(request, table_names), params.offset + len(rows)
        )
        last_page = min(math.ceil(total_estimate / params.size), max_page)

    return page_rows, {
        "last_page": last_page,
        "total": total,
        "total_estimate": total_estimate,
    }
