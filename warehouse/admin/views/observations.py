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


def _parse_days_param(request: Request, allowed: tuple[int, ...] = ALLOWED_DAYS) -> int:
    """Parse and validate the days query parameter."""
    try:
        days = int(request.params.get("days", DEFAULT_DAYS))
        return days if days in allowed else DEFAULT_DAYS
    except (ValueError, TypeError):
        return DEFAULT_DAYS


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


def _get_corroboration_stats(
    request: Request, cutoff_date: datetime
) -> tuple[dict, dict]:
    """
    Calculate corroboration and accuracy statistics for malware reports.

    Corroboration = multiple independent observers reporting the same package.
    Higher corroboration suggests higher confidence in the report.

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

    # Use window function to include report_count per package in each row
    stmt = select(
        Observation.related_name,  # type: ignore[attr-defined]
        Observation.related_id,  # type: ignore[attr-defined]
        Observation.actions,
        func.count()
        .over(partition_by=Observation.related_name)  # type: ignore[attr-defined]
        .label("report_count"),
    ).where(
        Observation.kind == "is_malware",
        Observation.created >= cutoff_date,
    )
    observations = request.db.execute(stmt).all()

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


def _get_observer_type_stats(request: Request, cutoff_date: datetime) -> dict:
    """
    Break down reports by observer type (trusted vs non-trusted).

    Trusted observers have is_observer=True on their user account.
    """

    # Get observations first
    obs_stmt = select(
        Observation.observer_id,  # type: ignore[attr-defined]
        Observation.actions,
        Observation.related_id,  # type: ignore[attr-defined]
    ).where(
        Observation.kind == "is_malware",
        Observation.created >= cutoff_date,
    )
    observations = request.db.execute(obs_stmt).all()

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


def _get_auto_quarantine_stats(request: Request, cutoff_date: datetime) -> dict:
    """
    Calculate auto-quarantine statistics.

    Auto-quarantined packages are identified by journal entries with
    action='project quarantined' submitted by 'admin' user.
    Uses related_name to include observations for deleted projects.
    """
    empty_result = {
        "total_reported": 0,
        "auto_quarantined": 0,
        "quarantine_rate": None,
    }

    # Get reported package names from observations (includes deleted projects)
    obs_stmt = select(Observation.related_name).where(  # type: ignore[attr-defined]
        Observation.kind == "is_malware",
        Observation.created >= cutoff_date,
    )
    observations = request.db.execute(obs_stmt).all()

    # Parse project names from related_name
    reported_names: set[str] = set()
    for obs in observations:
        name = _parse_project_name_from_repr(obs.related_name)
        if name:  # pragma: no cover
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

    Returns naive datetime for comparison with DB datetimes.
    """
    if not actions:
        return None

    removal_time = None
    for action_data in actions.values():
        if action_data.get("action") != "remove_malware":
            continue
        action_time = action_data.get("created_at")
        if not action_time:
            continue

        removal_dt = datetime.fromisoformat(action_time)
        # Strip timezone for comparison with naive DB datetimes
        if removal_dt.tzinfo is not None:
            removal_dt = removal_dt.replace(tzinfo=None)
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


def _get_timeline_data(request: Request, cutoff_date: datetime) -> tuple[dict, dict]:
    """
    Fetch and process timeline data for malware observations.

    Returns (project_data, quarantine_dates) where project_data contains
    per-project timeline information.

    All observations have related_name (always present) and created time.
    related_id indicates whether the project still exists (non-NULL = exists).
    Project creation times and quarantine times are looked up from JournalEntry.
    """
    # Get malware observations - no join needed
    obs_stmt = select(
        Observation.related_name,  # type: ignore[attr-defined]
        Observation.actions,
        Observation.created.label("report_created"),
    ).where(
        Observation.kind == "is_malware",
        Observation.created >= cutoff_date,
    )
    observations = request.db.execute(obs_stmt).all()

    if not observations:
        return {}, {}

    # Build project_data grouped by related_name, collecting project names
    project_data: dict = {}
    project_names: set[str] = set()

    for obs in observations:
        key = obs.related_name
        name = _parse_project_name_from_repr(obs.related_name)

        if name:  # pragma: no cover
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
            # Track the earliest removal
            obs_removal = _parse_removal_time(obs.actions)
            if obs_removal:  # pragma: no cover
                current = project_data[key]["removal_time"]
                if current is None or obs_removal < current:
                    project_data[key]["removal_time"] = obs_removal

    if not project_names:  # pragma: no cover
        return project_data, {}

    # Look up creation times from journal entries
    creation_stmt = (
        select(
            JournalEntry.name,
            func.min(JournalEntry.submitted_date).label("created_date"),
        )
        .where(
            JournalEntry.name.in_(project_names),
            JournalEntry.action == "create",
        )
        .group_by(JournalEntry.name)
    )
    creation_dates = {
        row.name: row.created_date for row in request.db.execute(creation_stmt).all()
    }

    # Look up quarantine times from journal entries
    quarantine_stmt = (
        select(
            JournalEntry.name,
            func.min(JournalEntry.submitted_date).label("quarantine_date"),
        )
        .where(
            JournalEntry.name.in_(project_names),
            JournalEntry.action == "project quarantined",
            JournalEntry._submitted_by == "admin",
        )
        .group_by(JournalEntry.name)
    )
    quarantine_dates = {
        q.name: q.quarantine_date for q in request.db.execute(quarantine_stmt).all()
    }

    # Fill in creation and quarantine times
    for data in project_data.values():
        if data["name"]:  # pragma: no cover
            data["project_created"] = creation_dates.get(data["name"])
            data["quarantine_time"] = quarantine_dates.get(data["name"])

    return project_data, quarantine_dates


def _calc_action_time(
    quarantine_time: datetime | None, removal_time: datetime | None
) -> datetime | None:
    """Calculate the earliest action time (quarantine or removal)."""
    if quarantine_time and removal_time:
        return min(quarantine_time, removal_time)
    return quarantine_time or removal_time


def _get_response_timeline_stats(request: Request, cutoff_date: datetime) -> dict:
    """
    Calculate response timeline statistics for confirmed malware.

    Measures how quickly malware is detected and actioned:
    - Time to Detection: Project creation -> First malware report
    - Time to Quarantine: First report -> Auto-quarantine (project unavailable)
    - Time to Removal: First report -> remove_malware action (project deleted)
    - Total Exposure: Project creation -> Quarantine or Removal (whichever is first)
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

    project_data, _ = _get_timeline_data(request, cutoff_date)
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

        # Time to Detection: project created -> first report
        if project_created and first_report:
            detection_hours = (first_report - project_created).total_seconds() / 3600
            if detection_hours >= 0:  # pragma: no cover
                detection_times.append(detection_hours)

        # Time to Quarantine: first report -> quarantine
        if quarantine_time and first_report:
            quarantine_hours = (quarantine_time - first_report).total_seconds() / 3600
            if quarantine_hours >= 0:  # pragma: no cover
                quarantine_times.append(quarantine_hours)

        # Time to Removal: first report -> removal
        if removal_time and first_report:
            removal_hours = (removal_time - first_report).total_seconds() / 3600
            if removal_hours >= 0:  # pragma: no cover
                removal_times.append(removal_hours)

        # Response Time: first report -> earliest action
        action_time = _calc_action_time(quarantine_time, removal_time)
        if action_time and first_report:  # pragma: no cover
            response_hours = (action_time - first_report).total_seconds() / 3600
            if response_hours >= 0:
                response_times.append(response_hours)

        # Total Exposure: project created -> earliest action
        if action_time and project_created:
            exposure_hours = (action_time - project_created).total_seconds() / 3600
            if exposure_hours >= 0:  # pragma: no cover
                exposure_times.append(exposure_hours)
                exposure_details.append(
                    {
                        "name": data["name"],
                        "exposure_hours": round(exposure_hours, 1),
                        "project_created": project_created,
                        "first_report": first_report,
                        "quarantine_time": quarantine_time,
                        "removal_time": removal_time,
                    }
                )

    def calc_stats(times: list) -> dict | None:
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

    # Sort by exposure and get top 5 longest-lived
    exposure_details.sort(key=lambda x: x["exposure_hours"], reverse=True)

    return {
        "sample_size": len(project_data),
        "detection_time": calc_stats(detection_times),
        "quarantine_time": calc_stats(quarantine_times),
        "removal_time": calc_stats(removal_times),
        "response_time": calc_stats(response_times),
        "total_exposure": calc_stats(exposure_times),
        "longest_lived": exposure_details[:5],
    }


def _get_timeline_trends(request: Request, cutoff_date: datetime) -> dict[str, list]:
    """
    Calculate weekly timeline trends for visualization.

    Returns weekly median values for detection, response, and time-to-quarantine.
    """
    empty_result: dict[str, list] = {
        "labels": [],
        "detection": [],
        "response": [],
        "time_to_quarantine": [],
    }

    project_data, _ = _get_timeline_data(request, cutoff_date)
    if not project_data:
        return empty_result

    # Group times by week
    weekly_data: dict[str, dict[str, list]] = {}

    for data in project_data.values():
        project_created = data["project_created"]
        first_report = data["first_report"]
        quarantine_time = data["quarantine_time"]
        removal_time = data["removal_time"]

        if not first_report:  # pragma: no cover
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
        if project_created:
            detection_hours = (first_report - project_created).total_seconds() / 3600
            if detection_hours >= 0:  # pragma: no cover
                weekly_data[week_key]["detection"].append(detection_hours)

        # Response time: first report -> action
        action_time = _calc_action_time(quarantine_time, removal_time)
        if action_time and first_report:
            response_hours = (action_time - first_report).total_seconds() / 3600
            if response_hours >= 0:
                weekly_data[week_key]["response"].append(response_hours)

        # Time to Quarantine: upload -> quarantine
        if quarantine_time and project_created:  # pragma: no cover
            ttq_hours = (quarantine_time - project_created).total_seconds() / 3600
            if ttq_hours >= 0:
                weekly_data[week_key]["time_to_quarantine"].append(ttq_hours)

    # Calculate medians for each week
    def median(values: list) -> float | None:
        if not values:
            return None
        values.sort()
        return round(values[len(values) // 2], 1)

    sorted_weeks = sorted(weekly_data.keys())
    labels = []
    detection_medians = []
    response_medians = []
    time_to_quarantine_medians = []

    for week in sorted_weeks:
        week_date = datetime.strptime(week, "%Y-%m-%d")
        labels.append(week_date.strftime("%b %d"))

        week_data = weekly_data[week]
        detection_medians.append(median(week_data["detection"]))
        response_medians.append(median(week_data["response"]))
        time_to_quarantine_medians.append(median(week_data["time_to_quarantine"]))

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

    corroboration, corroborated_accuracy = _get_corroboration_stats(
        request, cutoff_date
    )
    observer_types = _get_observer_type_stats(request, cutoff_date)
    auto_quarantine = _get_auto_quarantine_stats(request, cutoff_date)
    timeline = _get_response_timeline_stats(request, cutoff_date)
    timeline_trends = _get_timeline_trends(request, cutoff_date)

    return {
        "days": days,
        "corroboration": corroboration,
        "corroborated_accuracy": corroborated_accuracy,
        "observer_types": observer_types,
        "auto_quarantine": auto_quarantine,
        "timeline": timeline,
        "timeline_trends": timeline_trends,
    }
