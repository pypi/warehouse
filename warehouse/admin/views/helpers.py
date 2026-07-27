# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import TYPE_CHECKING

from psycopg.errors import QueryCanceled
from pyramid.httpexceptions import HTTPBadRequest
from sqlalchemy import func, select, text

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from typing import Any

    from pyramid.request import Request
    from sqlalchemy import Row, Select

# Valid time periods for filtering
ALLOWED_DAYS = (30, 60, 90)
DEFAULT_DAYS = 30


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
