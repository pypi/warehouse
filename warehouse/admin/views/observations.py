# SPDX-License-Identifier: Apache-2.0

"""Admin Views related to Observations"""
from __future__ import annotations

import re

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from pyramid.view import view_config
from sqlalchemy import func, select

from warehouse.accounts.models import User
from warehouse.authnz import Permissions
from warehouse.observations.models import Observation, Observer
from warehouse.observations.utils import calc_accuracy, classify_observation
from warehouse.packaging.models import JournalEntry

if TYPE_CHECKING:
    from pyramid.request import Request

# Valid time periods for filtering
ALLOWED_DAYS = (30, 60, 90)
DEFAULT_DAYS = 30

# Pattern to extract project name from related_name repr string
# Format: Project(id=..., name='project-name', ...)
_PROJECT_NAME_PATTERN = re.compile(r"name='([^']+)'")


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


def _parse_days_param(request: Request, allowed: tuple[int, ...] = ALLOWED_DAYS) -> int:
    """Parse and validate the days query parameter."""
    try:
        days = int(request.params.get("days", DEFAULT_DAYS))
        return days if days in allowed else DEFAULT_DAYS
    except (ValueError, TypeError):
        return DEFAULT_DAYS


def _fetch_malware_observations(request: Request, cutoff_date: datetime) -> list:
    """
    Fetch all malware observations with all fields needed by stats functions.

    This single query replaces multiple individual queries, reducing DB round trips.
    Uses a window function to include report_count per package in each row.
    """
    stmt = select(
        Observation.related_name,  # type: ignore[attr-defined]
        Observation.related_id,  # type: ignore[attr-defined]
        Observation.observer_id,  # type: ignore[attr-defined]
        Observation.actions,
        Observation.created.label("report_created"),
        func.count()
        .over(partition_by=Observation.related_name)  # type: ignore[attr-defined]
        .label("report_count"),
    ).where(
        Observation.kind == "is_malware",
        Observation.created >= cutoff_date,
    )
    return request.db.execute(stmt).all()


@view_config(
    route_name="admin.observations.list",
    renderer="warehouse.admin:templates/admin/observations/list.html",
    permission=Permissions.AdminObservationsRead,
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def observations_list(request):
    """
    List all Observations.

    TODO: Should we filter server-side by `kind`, or in the template?
     Currently the server returns all observations, and then we group them by kind
     for display in the template.

    TODO: Paginate this view, not worthwhile just yet.
    """

    observations = (
        request.db.query(Observation).order_by(Observation.created.desc()).all()
    )

    # Group observations by kind
    grouped_observations = defaultdict(list)
    for observation in observations:
        grouped_observations[observation.kind].append(observation)

    return {"kind_groups": grouped_observations}


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

        removal_dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
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
                "removal_time": _parse_removal_time(obs.actions),
            }
        else:
            # Track the earliest report
            if obs.report_created < project_data[key]["first_report"]:
                project_data[key]["first_report"] = obs.report_created
            # Track the earliest removal - only parse if we might update
            current_removal = project_data[key]["removal_time"]
            if obs.actions:  # Only parse if actions exist
                obs_removal = _parse_removal_time(obs.actions)
                if obs_removal and (
                    current_removal is None or obs_removal < current_removal
                ):
                    project_data[key]["removal_time"] = obs_removal

    if not project_names:
        return project_data

    # Look up creation and quarantine times from journal entries in one query
    # Using conditional aggregation to get both in a single round-trip
    journal_stmt = (
        select(
            JournalEntry.name,
            func.min(JournalEntry.submitted_date)
            .filter(JournalEntry.action == "create")
            .label("created_date"),
            func.min(JournalEntry.submitted_date)
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
    days = _parse_days_param(request)
    cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=days)

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
