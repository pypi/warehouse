# SPDX-License-Identifier: Apache-2.0

"""Admin Views related to Observations"""

from __future__ import annotations

import re

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import packaging.utils

from pyramid.httpexceptions import HTTPBadRequest
from pyramid.view import view_config
from sqlalchemy import func, or_, select, text

from warehouse.accounts.models import User
from warehouse.admin.views.helpers import parse_days_param
from warehouse.authnz import Permissions
from warehouse.observations.models import (
    OBSERVATION_KIND_MAP,
    Observation,
    ObservationKind,
    Observer,
)
from warehouse.observations.utils import calc_accuracy, classify_observation
from warehouse.organizations.models import OrganizationApplication
from warehouse.packaging.models import JournalEntry, Project

if TYPE_CHECKING:
    from typing import Any
    from uuid import UUID

    from pyramid.request import Request
    from sqlalchemy import Select
    from sqlalchemy.sql import ColumnElement

# Pattern to extract project name from related_name repr string
# Format: Project(id=..., name='project-name', ...)
_PROJECT_NAME_PATTERN = re.compile(r"name='([^']+)'")

# Server-side DataTables constants
_MAX_PAGE_LENGTH = 100
_MAX_SEARCH_LENGTH = 500
_DEFAULT_PAGE_LENGTH = 25

# Filtering by kind lets us query the single concrete observation table for that
# kind instead of the polymorphic UNION over every *_observations table.
_KIND_TO_MODEL: dict[str, type[Observation]] = {
    "is_malware": Project.Observation,
    "is_dependency_confusion": Project.Observation,
    "is_spam": Project.Observation,
    "something_else": Project.Observation,
    "account_abuse": User.Observation,
    "account_recovery": User.Observation,
    "email_unverified": User.Observation,
    "information_request": OrganizationApplication.Observation,
}

_KIND_TO_ADMIN_ROUTE: dict[str, str] = {
    "is_malware": "admin.project.detail",
    "is_dependency_confusion": "admin.project.detail",
    "is_spam": "admin.project.detail",
    "something_else": "admin.project.detail",
    "account_abuse": "admin.user.detail",
    "account_recovery": "admin.user.detail",
    "email_unverified": "admin.user.detail",
    "information_request": "admin.organization_application.detail",
}

# Allowlist of DataTables `columns[i][name]` values that may drive ORDER BY.
# Every entry's name is also a column attribute on the concrete tables.
_SORTABLE_COLUMNS: frozenset[str] = frozenset({"created", "kind"})

_OBSERVATION_TABLE_NAMES: tuple[str, ...] = tuple(
    cls.__tablename__ for cls in Observation.__subclasses__()
)


@dataclass(frozen=True)
class _DataTablesParams:
    draw: int
    start: int
    length: int
    search_value: str
    sort_column: str
    sort_dir: str
    kind_filter: str | None


def _parse_datatables_params(params: Mapping[str, str]) -> _DataTablesParams:
    """Parse and validate the DataTables 1.10+ server-side query params."""
    try:
        draw = int(params.get("draw", "1"))
    except (TypeError, ValueError):
        raise HTTPBadRequest("'draw' must be an integer.") from None

    try:
        start = max(0, int(params.get("start", "0")))
    except (TypeError, ValueError):
        raise HTTPBadRequest("'start' must be an integer.") from None

    try:
        raw_length = int(params.get("length", str(_DEFAULT_PAGE_LENGTH)))
    except (TypeError, ValueError):
        raise HTTPBadRequest("'length' must be an integer.") from None
    if raw_length == -1:
        length = _MAX_PAGE_LENGTH
    elif raw_length <= 0:
        length = 1
    else:
        length = min(raw_length, _MAX_PAGE_LENGTH)

    search_value = (params.get("search[value]") or "").strip()
    if len(search_value) > _MAX_SEARCH_LENGTH:
        raise HTTPBadRequest(
            f"'search[value]' must be <= {_MAX_SEARCH_LENGTH} characters."
        )

    sort_column = "created"
    sort_dir = "desc"
    order_idx_raw = params.get("order[0][column]")
    if order_idx_raw is not None:
        try:
            order_idx = int(order_idx_raw)
        except (TypeError, ValueError):
            raise HTTPBadRequest("'order[0][column]' must be an integer.") from None
        requested_dir = params.get("order[0][dir]", "desc")
        if requested_dir not in ("asc", "desc"):
            raise HTTPBadRequest("'order[0][dir]' must be 'asc' or 'desc'.")
        sort_dir = requested_dir
        col_name = params.get(f"columns[{order_idx}][name]")
        if col_name in _SORTABLE_COLUMNS:
            sort_column = col_name

    kind_filter: str | None = None
    # Find the kind column's per-column search value. DataTables sends
    # columns[0..N]; we stop when we encounter an index with no [name].
    i = 0
    while True:
        col_name = params.get(f"columns[{i}][name]")
        if col_name is None:
            break
        if col_name == "kind":
            raw_kind = (params.get(f"columns[{i}][search][value]") or "").strip()
            if raw_kind and raw_kind in OBSERVATION_KIND_MAP:
                kind_filter = raw_kind
            break
        i += 1

    return _DataTablesParams(
        draw=draw,
        start=start,
        length=length,
        search_value=search_value,
        sort_column=sort_column,
        sort_dir=sort_dir,
        kind_filter=kind_filter,
    )


def _base_and_conditions(
    params: _DataTablesParams,
) -> tuple[type[Observation], list[ColumnElement[bool]]]:
    """Pick the query target and build the WHERE conditions for a request.

    When kind is filtered we target the single concrete observation table;
    without a filter we fall back to the polymorphic union. The concrete table
    can still hold multiple kinds (e.g. project_observations holds is_malware,
    is_spam, ...), so the kind predicate is retained.
    """
    base: type[Observation] = (
        _KIND_TO_MODEL[params.kind_filter] if params.kind_filter else Observation
    )
    conditions: list[ColumnElement[bool]] = []
    if params.kind_filter:
        conditions.append(base.kind == params.kind_filter)
    if params.search_value:
        pattern = f"%{params.search_value}%"
        conditions.append(
            or_(base.summary.ilike(pattern), base.related_name.ilike(pattern))
        )
    return base, conditions


def _build_observations_query(params: _DataTablesParams) -> Select[Any]:
    """Build the main paginated SELECT with a windowed filtered count."""
    base, conditions = _base_and_conditions(params)
    sort_col = getattr(base, params.sort_column)
    order_clause = sort_col.desc() if params.sort_dir == "desc" else sort_col.asc()

    return (
        select(
            base.id,
            base.created,
            base.kind,
            base.summary,
            base.related_name,
            base.related_id,
            base.observer_id,
            func.count().over().label("total_filtered"),
        )
        .where(*conditions)
        .order_by(order_clause)
        .limit(params.length)
        .offset(params.start)
    )


def _count_filtered(request: Request, params: _DataTablesParams) -> int:
    """Count matching rows when the page is empty but a filter is active."""
    base, conditions = _base_and_conditions(params)
    return (
        request.db.scalar(select(func.count()).select_from(base).where(*conditions))
        or 0
    )


def _count_all_observations(request: Request) -> int:
    """Estimate unfiltered total via pg_class.reltuples — sub-millisecond."""
    result = request.db.execute(
        text(
            "SELECT COALESCE(SUM(reltuples)::bigint, 0) FROM pg_class "
            "WHERE relname = ANY(:names) AND relkind = 'r'"
        ),
        {"names": list(_OBSERVATION_TABLE_NAMES)},
    ).scalar()
    return int(result or 0)


def _resolve_observers(
    request: Request, observer_ids: set[UUID]
) -> dict[UUID, str | None]:
    if not observer_ids:
        return {}
    stmt = (
        select(Observer.id, User.username)
        .select_from(Observer)
        .outerjoin(User, User.observer_association_id == Observer._association_id)
        .where(Observer.id.in_(observer_ids))
    )
    return {row.id: row.username for row in request.db.execute(stmt).all()}


def _build_related_link(
    request: Request,
    kind: str,
    parsed_name: str | None,
    related_id: UUID | None,
) -> str | None:
    """Build the admin URL for an observation's related object, or None."""
    if related_id is None:
        return None
    route = _KIND_TO_ADMIN_ROUTE.get(kind)
    if route is None:  # pragma: no cover -- every ObservationKind has a mapping
        return None
    if route == "admin.project.detail":
        if not parsed_name:
            return None
        return request.route_path(
            route, project_name=packaging.utils.canonicalize_name(parsed_name)
        )
    if route == "admin.user.detail":
        if not parsed_name:
            return None
        return request.route_path(route, username=parsed_name)
    if route == "admin.organization_application.detail":
        return request.route_path(route, organization_application_id=str(related_id))
    return None  # pragma: no cover -- all routes covered above


def _render_datatables_payload(request: Request) -> dict[str, Any]:
    params = _parse_datatables_params(request.params)
    stmt = _build_observations_query(params)
    rows = request.db.execute(stmt).all()

    if rows:
        records_filtered = rows[0].total_filtered
    elif params.start > 0 or params.search_value or params.kind_filter:
        records_filtered = _count_filtered(request, params)
    else:
        records_filtered = 0

    observer_usernames = _resolve_observers(request, {row.observer_id for row in rows})

    data: list[dict[str, Any]] = []
    for row in rows:
        parsed_name = _parse_project_name_from_repr(row.related_name)
        display = parsed_name or row.related_name
        related_link = _build_related_link(
            request, row.kind, parsed_name, row.related_id
        )

        username = observer_usernames.get(row.observer_id)
        observer_link = (
            request.route_path("admin.user.detail", username=username)
            if username
            else None
        )

        kind_display = (
            OBSERVATION_KIND_MAP[row.kind].value[1]
            if row.kind in OBSERVATION_KIND_MAP
            else row.kind
        )

        data.append(
            {
                "created": row.created.isoformat() if row.created else None,
                "kind": row.kind,
                "kind_display": kind_display,
                "related": display,
                "related_link": related_link,
                "summary": row.summary,
                "observer": username or "",
                "observer_link": observer_link,
            }
        )

    return {
        "draw": params.draw,
        "recordsTotal": _count_all_observations(request),
        "recordsFiltered": records_filtered,
        "data": data,
    }


def _calc_stats(times: list) -> dict | None:
    """Calculate statistical summary for a list of time values."""
    if not times:
        return None
    times.sort()
    n = len(times)
    return {
        "median": round(times[n // 2], 1),
        "average": round(sum(times) / n, 1),
        "p90": round(times[int(n * 0.9)] if n >= 10 else times[-1], 1),
        "min": round(min(times), 1),
        "max": round(max(times), 1),
        "count": n,
    }


def _calc_median(values: list) -> float | None:
    """Calculate median of a list of values."""
    if not values:
        return None
    values.sort()
    return round(values[len(values) // 2], 1)


def _fetch_malware_observations(request: Request, cutoff_date: datetime) -> list:
    """
    Fetch all malware observations with all fields needed by stats functions.

    This single query replaces multiple individual queries, reducing DB round trips.
    Uses a window function to include report_count per package in each row.
    """
    stmt = select(
        Observation.related_name,
        Observation.related_id,
        Observation.observer_id,
        Observation.actions,
        Observation.created.label("report_created"),
        func.count().over(partition_by=Observation.related_name).label("report_count"),
    ).where(
        Observation.kind == "is_malware",
        Observation.created >= cutoff_date,
    )
    return request.db.execute(stmt).all()


@view_config(
    route_name="admin.observations.list",
    renderer="warehouse.admin:templates/admin/observations/list.html",
    accept="text/html",
    permission=Permissions.AdminObservationsRead,
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def observations_list(request: Request) -> dict[str, Any]:
    return {"observation_kinds": list(ObservationKind)}


@view_config(
    route_name="admin.observations.list",
    renderer="json",
    accept="application/json",
    permission=Permissions.AdminObservationsRead,
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def observations_list_json(request: Request) -> dict[str, Any]:
    return _render_datatables_payload(request)


def _get_corroboration_stats(observations: list) -> tuple[dict, dict]:
    """
    Calculate corroboration and accuracy statistics for malware reports.

    Corroboration = multiple independent observers reporting the same package.
    Higher corroboration suggests higher confidence in the report.

    Args:
        observations: Pre-fetched observations from _fetch_malware_observations()

    Returns tuple of (corroboration_stats, accuracy_stats).
    """
    empty_corroboration = {
        "total_packages": 0,
        "single_report_packages": 0,
        "multi_report_packages": 0,
        "total_reports": 0,
        "corroborated_reports": 0,
        "corroboration_rate": None,
    }
    empty_accuracy = {
        "single": {"total": 0, "true_pos": 0, "false_pos": 0, "accuracy": None},
        "multi": {"total": 0, "true_pos": 0, "false_pos": 0, "accuracy": None},
    }

    if not observations:
        return empty_corroboration, empty_accuracy

    # Classify each observation and track package counts
    seen_packages: set[str] = set()
    single_report_packages = 0
    multi_report_packages = 0
    corroborated_reports = 0
    single_accuracy: dict = {"total": 0, "true_pos": 0, "false_pos": 0}
    multi_accuracy: dict = {"total": 0, "true_pos": 0, "false_pos": 0}

    for obs in observations:
        is_multi = obs.report_count >= 2

        # Track unique packages (only count once per package)
        if obs.related_name not in seen_packages:
            seen_packages.add(obs.related_name)
            if is_multi:
                multi_report_packages += 1
                corroborated_reports += obs.report_count
            else:
                single_report_packages += 1

        # Classify and bucket by single vs multi
        bucket = multi_accuracy if is_multi else single_accuracy
        bucket["total"] += 1

        verdict = classify_observation(obs.actions, obs.related_id)
        if verdict == "true_positive":
            bucket["true_pos"] += 1
        elif verdict == "false_positive":
            bucket["false_pos"] += 1

    total_reports = len(observations)
    corroboration_rate = (
        round((corroborated_reports / total_reports) * 100, 1)
        if total_reports > 0
        else None
    )

    single_accuracy["accuracy"] = calc_accuracy(
        single_accuracy["true_pos"], single_accuracy["false_pos"]
    )
    multi_accuracy["accuracy"] = calc_accuracy(
        multi_accuracy["true_pos"], multi_accuracy["false_pos"]
    )

    corroboration = {
        "total_packages": len(seen_packages),
        "single_report_packages": single_report_packages,
        "multi_report_packages": multi_report_packages,
        "total_reports": total_reports,
        "corroborated_reports": corroborated_reports,
        "corroboration_rate": corroboration_rate,
    }

    return corroboration, {"single": single_accuracy, "multi": multi_accuracy}


def _get_observer_type_stats(request: Request, observations: list) -> dict:
    """
    Break down reports by observer type (trusted vs non-trusted).

    Trusted observers have is_observer=True on their user account.

    Args:
        request: Pyramid request (needed for user lookup)
        observations: Pre-fetched observations from _fetch_malware_observations()
    """
    if not observations:
        return {
            "trusted": {"total": 0, "true_pos": 0, "false_pos": 0, "accuracy": None},
            "non_trusted": {
                "total": 0,
                "true_pos": 0,
                "false_pos": 0,
                "accuracy": None,
            },
        }

    # Get observer -> user mapping for is_observer status
    observer_ids = list({obs.observer_id for obs in observations})
    user_stmt = (
        select(Observer.id, User.is_observer)
        .select_from(Observer)
        .outerjoin(User, User.observer_association_id == Observer._association_id)
        .where(Observer.id.in_(observer_ids))
    )
    user_info = request.db.execute(user_stmt).all()
    observer_trusted = {row[0]: row[1] or False for row in user_info}

    trusted: dict = {"total": 0, "true_pos": 0, "false_pos": 0}
    non_trusted: dict = {"total": 0, "true_pos": 0, "false_pos": 0}

    for obs in observations:
        is_trusted = observer_trusted.get(obs.observer_id, False)
        bucket = trusted if is_trusted else non_trusted
        bucket["total"] += 1

        verdict = classify_observation(obs.actions, obs.related_id)
        if verdict == "true_positive":
            bucket["true_pos"] += 1
        elif verdict == "false_positive":
            bucket["false_pos"] += 1

    # Calculate accuracy rates
    for bucket in [trusted, non_trusted]:
        bucket["accuracy"] = calc_accuracy(bucket["true_pos"], bucket["false_pos"])

    return {"trusted": trusted, "non_trusted": non_trusted}


def _get_auto_quarantine_stats(
    request: Request, observations: list, cutoff_date: datetime
) -> dict:
    """
    Calculate auto-quarantine statistics.

    Auto-quarantined packages are identified by journal entries with
    action='project quarantined' submitted by 'admin' user.
    Uses related_name to include observations for deleted projects.

    Args:
        request: Pyramid request (needed for journal query)
        observations: Pre-fetched observations from _fetch_malware_observations()
        cutoff_date: Cutoff date for journal entry lookup
    """
    empty_result = {
        "total_reported": 0,
        "auto_quarantined": 0,
        "quarantine_rate": None,
    }

    if not observations:
        return empty_result

    # Parse project names from related_name
    reported_names: set[str] = set()
    for obs in observations:
        name = _parse_project_name_from_repr(obs.related_name)
        if name:
            reported_names.add(name)

    if not reported_names:
        return empty_result

    # Count auto-quarantined packages (by admin user)
    quarantine_stmt = select(func.count(func.distinct(JournalEntry.name))).where(
        JournalEntry.name.in_(reported_names),
        JournalEntry.action == "project quarantined",
        JournalEntry._submitted_by == "admin",
        JournalEntry.submitted_date >= cutoff_date,
    )
    auto_quarantined = request.db.scalar(quarantine_stmt) or 0

    total_reported = len(reported_names)
    quarantine_rate = (
        round((auto_quarantined / total_reported) * 100, 1)
        if total_reported > 0
        else None
    )

    return {
        "total_reported": total_reported,
        "auto_quarantined": auto_quarantined,
        "quarantine_rate": quarantine_rate,
    }


def _parse_removal_time(actions: dict | None) -> datetime | None:
    """
    Extract the earliest removal time from observation actions.

    Actions dict is keyed by unix timestamp, so we use that directly.
    Returns naive datetime for comparison with DB datetimes.
    """
    if not actions:
        return None

    removal_time = None
    for timestamp, action_data in actions.items():
        if action_data.get("action") != "remove_malware":
            continue

        removal_dt = datetime.fromtimestamp(int(timestamp), tz=UTC)
        removal_dt = removal_dt.replace(tzinfo=None)  # naive for DB comparison
        if removal_time is None or removal_dt < removal_time:
            removal_time = removal_dt

    return removal_time


def _parse_project_name_from_repr(related_name: str) -> str | None:
    """
    Extract project name from a related_name repr string.

    Format: Project(id=..., name='project-name', ...)
    Returns None if the pattern doesn't match.
    """
    match = _PROJECT_NAME_PATTERN.search(related_name)
    return match.group(1) if match else None


def _get_timeline_data(request: Request, observations: list) -> dict:
    """
    Process timeline data for malware observations.

    Args:
        request: Pyramid request (needed for journal queries)
        observations: Pre-fetched observations from _fetch_malware_observations()

    Returns project_data dict containing per-project timeline information.

    All observations have related_name (always present) and created time.
    related_id indicates whether the project still exists (non-NULL = exists).
    Project creation times and quarantine times are looked up from JournalEntry.
    """
    if not observations:
        return {}

    # Build project_data grouped by related_name, collecting project names
    project_data: dict = {}
    project_names: set[str] = set()

    for obs in observations:
        key = obs.related_name
        name = _parse_project_name_from_repr(obs.related_name)

        if name:
            project_names.add(name)

        if key not in project_data:
            project_data[key] = {
                "name": name,
                "project_created": None,  # Looked up from JournalEntry
                "first_report": obs.report_created,
                "quarantine_time": None,
                "removal_time": None,
            }

        entry = project_data[key]
        # Track the earliest report
        if obs.report_created < entry["first_report"]:
            entry["first_report"] = obs.report_created
        # Track the earliest removal across all observations for this project
        obs_removal = _parse_removal_time(obs.actions)
        if obs_removal and (
            entry["removal_time"] is None or obs_removal < entry["removal_time"]
        ):
            entry["removal_time"] = obs_removal

    if not project_names:
        return project_data

    # Look up creation and quarantine times from journal entries in one query
    # Using conditional aggregation to get both in a single round-trip
    # NOTE: We use func.max() to get the MOST RECENT create/quarantine times.
    # Projects can be removed and recreated (e.g., name squatting after removal),
    # so we need the latest "create" to accurately measure detection time for
    # the malicious instance, not the original legitimate project.
    journal_stmt = (
        select(
            JournalEntry.name,
            func.max(JournalEntry.submitted_date)
            .filter(JournalEntry.action == "create")
            .label("created_date"),
            func.max(JournalEntry.submitted_date)
            .filter(
                JournalEntry.action == "project quarantined",
                JournalEntry._submitted_by == "admin",
            )
            .label("quarantine_date"),
        )
        .where(JournalEntry.name.in_(project_names))
        .group_by(JournalEntry.name)
    )
    journal_data = {
        row.name: (row.created_date, row.quarantine_date)
        for row in request.db.execute(journal_stmt).all()
    }

    # Fill in creation and quarantine times
    for data in project_data.values():
        if data["name"] and data["name"] in journal_data:
            created, quarantined = journal_data[data["name"]]
            data["project_created"] = created
            data["quarantine_time"] = quarantined

    return project_data


def _calc_action_time(
    quarantine_time: datetime | None, removal_time: datetime | None
) -> datetime | None:
    """Calculate the earliest action time (quarantine or removal)."""
    if quarantine_time and removal_time:
        return min(quarantine_time, removal_time)
    return quarantine_time or removal_time


def _hours_between(start: datetime | None, end: datetime | None) -> float | None:
    """
    Calculate hours between two timestamps.

    Returns None if either timestamp is missing or if the result would be negative
    (which indicates data inconsistency - e.g., removal before report).
    """
    if not start or not end:
        return None
    hours = (end - start).total_seconds() / 3600
    return hours if hours >= 0 else None


def _get_response_timeline_stats(project_data: dict) -> dict:
    """
    Calculate response timeline statistics for confirmed malware.

    Measures how quickly malware is detected and actioned:
    - Time to Detection: Project creation -> First malware report
    - Time to Quarantine: First report -> Auto-quarantine (project unavailable)
    - Time to Removal: First report -> remove_malware action (project deleted)
    - Total Exposure: Project creation -> Quarantine or Removal (whichever is first)

    Args:
        project_data: Pre-computed project data from _get_timeline_data()
    """
    empty_result: dict = {
        "sample_size": 0,
        "detection_time": None,
        "quarantine_time": None,
        "removal_time": None,
        "response_time": None,
        "total_exposure": None,
        "longest_lived": [],
    }

    if not project_data:
        return empty_result

    # Calculate timelines
    detection_times = []
    quarantine_times = []
    removal_times = []
    response_times = []
    exposure_times = []
    exposure_details = []

    for data in project_data.values():
        project_created = data["project_created"]
        first_report = data["first_report"]
        quarantine_time = data["quarantine_time"]
        removal_time = data["removal_time"]
        action_time = _calc_action_time(quarantine_time, removal_time)

        # Time to Detection: project created -> first report
        if (hours := _hours_between(project_created, first_report)) is not None:
            detection_times.append(hours)

        # Time to Quarantine: first report -> quarantine
        if (hours := _hours_between(first_report, quarantine_time)) is not None:
            quarantine_times.append(hours)

        # Time to Removal: first report -> removal
        if (hours := _hours_between(first_report, removal_time)) is not None:
            removal_times.append(hours)

        # Response Time: first report -> earliest action
        if (hours := _hours_between(first_report, action_time)) is not None:
            response_times.append(hours)

        # Total Exposure: project created -> earliest action
        if (hours := _hours_between(project_created, action_time)) is not None:
            exposure_times.append(hours)
            exposure_details.append(
                {
                    "name": data["name"],
                    "exposure_hours": round(hours, 1),
                    "project_created": project_created,
                    "first_report": first_report,
                    "quarantine_time": quarantine_time,
                    "removal_time": removal_time,
                }
            )

    # Sort by exposure and get top 5 longest-lived
    exposure_details.sort(key=lambda x: x["exposure_hours"], reverse=True)

    return {
        "sample_size": len(project_data),
        "detection_time": _calc_stats(detection_times),
        "quarantine_time": _calc_stats(quarantine_times),
        "removal_time": _calc_stats(removal_times),
        "response_time": _calc_stats(response_times),
        "total_exposure": _calc_stats(exposure_times),
        "longest_lived": exposure_details[:5],
    }


def _get_timeline_trends(project_data: dict) -> dict[str, list]:
    """
    Calculate weekly timeline trends for visualization.

    Returns weekly median values for detection, response, and time-to-quarantine.

    Args:
        project_data: Pre-computed project data from _get_timeline_data()
    """
    empty_result: dict[str, list] = {
        "labels": [],
        "detection": [],
        "response": [],
        "time_to_quarantine": [],
    }

    if not project_data:
        return empty_result

    # Group times by week
    weekly_data: dict[str, dict[str, list]] = {}

    for data in project_data.values():
        project_created = data["project_created"]
        first_report = data["first_report"]
        quarantine_time = data["quarantine_time"]
        removal_time = data["removal_time"]
        action_time = _calc_action_time(quarantine_time, removal_time)

        if not first_report:
            continue

        # Use the week of the first report as the grouping key
        week_start = first_report - timedelta(days=first_report.weekday())
        week_key = week_start.strftime("%Y-%m-%d")

        if week_key not in weekly_data:
            weekly_data[week_key] = {
                "detection": [],
                "response": [],
                "time_to_quarantine": [],
            }

        # Detection time: upload -> first report
        if (hours := _hours_between(project_created, first_report)) is not None:
            weekly_data[week_key]["detection"].append(hours)

        # Response time: first report -> action
        if (hours := _hours_between(first_report, action_time)) is not None:
            weekly_data[week_key]["response"].append(hours)

        # Time to Quarantine: upload -> quarantine
        if (hours := _hours_between(project_created, quarantine_time)) is not None:
            weekly_data[week_key]["time_to_quarantine"].append(hours)

    # Calculate medians for each week
    sorted_weeks = sorted(weekly_data.keys())
    labels = []
    detection_medians = []
    response_medians = []
    time_to_quarantine_medians = []

    for week in sorted_weeks:
        week_date = datetime.strptime(week, "%Y-%m-%d")
        labels.append(week_date.strftime("%b %d"))

        week_data = weekly_data[week]
        detection_medians.append(_calc_median(week_data["detection"]))
        response_medians.append(_calc_median(week_data["response"]))
        time_to_quarantine_medians.append(_calc_median(week_data["time_to_quarantine"]))

    return {
        "labels": labels,
        "detection": detection_medians,
        "response": response_medians,
        "time_to_quarantine": time_to_quarantine_medians,
    }


@view_config(
    route_name="admin.observations.insights",
    renderer="warehouse.admin:templates/admin/observations/insights.html",
    permission=Permissions.AdminObservationsRead,
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def observations_insights(request: Request):
    """Display report quality insights and response timeline metrics."""
    days = parse_days_param(request)
    cutoff_date = datetime.now(tz=UTC) - timedelta(days=days)

    observations = _fetch_malware_observations(request, cutoff_date)

    # Process observations through each stats function
    corroboration, corroborated_accuracy = _get_corroboration_stats(observations)
    observer_types = _get_observer_type_stats(request, observations)
    auto_quarantine = _get_auto_quarantine_stats(request, observations, cutoff_date)

    # Single call for timeline data - used by both timeline stats and trends
    project_data = _get_timeline_data(request, observations)
    timeline = _get_response_timeline_stats(project_data)
    timeline_trends = _get_timeline_trends(project_data)

    return {
        "days": days,
        "corroboration": corroboration,
        "corroborated_accuracy": corroborated_accuracy,
        "observer_types": observer_types,
        "auto_quarantine": auto_quarantine,
        "timeline": timeline,
        "timeline_trends": timeline_trends,
    }
