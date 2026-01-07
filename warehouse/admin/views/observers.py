# SPDX-License-Identifier: Apache-2.0

"""Admin Views for Observer Reputation tracking."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from pyramid.httpexceptions import HTTPNotFound
from pyramid.view import view_config
from sqlalchemy import select

from warehouse.authnz import Permissions
from warehouse.observations.models import Observation, Observer

if TYPE_CHECKING:
    from pyramid.request import Request

# Valid time periods for filtering
ALLOWED_DAYS = (30, 60, 90)
ALLOWED_DAYS_DETAIL = (30, 60, 90, 0)  # 0 = lifetime (no limit)
DEFAULT_DAYS = 30


def _classify_observation(actions: dict | None, related_id) -> str:
    """
    Classify an observation as true_positive, false_positive, or pending.

    Classification rules:
    - true_positive: has 'remove_malware' action OR project removed (related_id=None)
    - false_positive: has 'verdict_not_malware' action (only if no remove_malware)
    - pending: no verdict yet
    """
    if not actions:
        return "true_positive" if related_id is None else "pending"

    has_not_malware = False
    for action_data in actions.values():
        action = action_data.get("action", "")
        if action == "remove_malware":
            return "true_positive"  # Takes precedence, return immediately
        if action == "verdict_not_malware":
            has_not_malware = True

    return "false_positive" if has_not_malware else "pending"


def _parse_days_param(request: Request, allowed: tuple[int, ...] = ALLOWED_DAYS) -> int:
    """Parse and validate the days query parameter."""
    try:
        days = int(request.params.get("days", DEFAULT_DAYS))
        return days if days in allowed else DEFAULT_DAYS
    except (ValueError, TypeError):
        return DEFAULT_DAYS


def _get_malware_observations(request: Request, days: int):
    """
    Fetch all malware observations within the time period.

    Returns raw observation data (observer_id, actions, related_id, created).
    """
    cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=days)

    stmt = select(
        Observation.observer_id,  # type: ignore[attr-defined]
        Observation.actions,
        Observation.related_id,  # type: ignore[attr-defined]
        Observation.created,
    ).where(
        Observation.kind == "is_malware",
        Observation.created >= cutoff_date,
    )
    return request.db.execute(stmt).all()


def _get_observer_stats(request: Request, observations: list) -> list[dict]:
    """
    Aggregate observations into per-observer statistics.

    Returns a sorted list of dicts with observer stats including:
    - observer_id, username, user_id
    - total_observations, true_positives, false_positives, pending
    - accuracy_rate, score
    """
    if not observations:
        return []

    # Aggregate by observer
    stats_by_observer: dict = defaultdict(
        lambda: {
            "total_observations": 0,
            "true_positives": 0,
            "false_positives": 0,
            "pending": 0,
        }
    )

    for obs in observations:
        stats = stats_by_observer[obs.observer_id]
        stats["total_observations"] += 1

        verdict = _classify_observation(obs.actions, obs.related_id)
        if verdict == "true_positive":
            stats["true_positives"] += 1
        elif verdict == "false_positive":
            stats["false_positives"] += 1
        else:
            stats["pending"] += 1

    # Fetch observer info in single query
    observer_ids = list(stats_by_observer.keys())
    stmt = select(Observer).where(Observer.id.in_(observer_ids))
    observers = request.db.scalars(stmt).all()

    observer_map = {
        o.id: (
            (o.parent.username, o.parent.id) if o.parent else (f"Observer {o.id}", None)
        )
        for o in observers
    }

    # Build result with calculated fields
    result = []
    for observer_id, stats in stats_by_observer.items():
        default = (f"Observer {observer_id}", None)
        username, user_id = observer_map.get(observer_id, default)

        resolved = stats["true_positives"] + stats["false_positives"]
        accuracy_rate = (
            round((stats["true_positives"] / resolved) * 100, 1)
            if resolved > 0
            else None
        )
        score = (stats["true_positives"] * 2) - stats["false_positives"]

        result.append(
            {
                "observer_id": observer_id,
                "username": username,
                "user_id": user_id,
                "accuracy_rate": accuracy_rate,
                "score": score,
                **stats,
            }
        )

    # Sort by: score (desc), accuracy (desc), total observations (desc)
    result.sort(
        key=lambda x: (x["score"], x["accuracy_rate"] or 0, x["total_observations"]),
        reverse=True,
    )

    return result


def _aggregate_weekly_time_series(observations) -> dict:
    """
    Aggregate observations into weekly time series data for Chart.js.

    Accepts any iterable of objects with .created, .actions, and .related_id attributes.
    Returns dict with labels and counts for true_positives, false_positives, pending.
    """
    if not observations:
        return {
            "labels": [],
            "true_positives": [],
            "false_positives": [],
            "pending": [],
        }

    weekly_data: dict[str, dict[str, int]] = defaultdict(
        lambda: {"true_positives": 0, "false_positives": 0, "pending": 0}
    )

    for obs in observations:
        # Get the start of the week (Monday)
        week_start = obs.created - timedelta(days=obs.created.weekday())
        week_key = week_start.strftime("%Y-%m-%d")

        verdict = _classify_observation(obs.actions, obs.related_id)
        weekly_data[week_key][
            verdict.replace("true_positive", "true_positives").replace(
                "false_positive", "false_positives"
            )
        ] += 1

    # Convert to sorted lists for Chart.js
    sorted_weeks = sorted(weekly_data.keys())
    return {
        "labels": sorted_weeks,
        "true_positives": [weekly_data[w]["true_positives"] for w in sorted_weeks],
        "false_positives": [weekly_data[w]["false_positives"] for w in sorted_weeks],
        "pending": [weekly_data[w]["pending"] for w in sorted_weeks],
    }


def _get_observer_detail_stats(request: Request, observer: Observer, days: int) -> dict:
    """
    Get detailed observations for a specific observer, grouped by verdict.

    If days=0, returns all observations (lifetime).
    """
    stmt = select(Observation).where(
        Observation.observer_id == observer.id,  # type: ignore[attr-defined]
        Observation.kind == "is_malware",
    )

    if days > 0:
        cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=days)
        stmt = stmt.where(Observation.created >= cutoff_date)

    stmt = stmt.order_by(Observation.created.desc())
    observations = request.db.scalars(stmt).all()

    categorized: dict[str, list] = {
        "true_positives": [],
        "false_positives": [],
        "pending": [],
    }

    for obs in observations:
        verdict = _classify_observation(obs.actions, obs.related_id)
        if verdict == "true_positive":
            categorized["true_positives"].append(obs)
        elif verdict == "false_positive":
            categorized["false_positives"].append(obs)
        else:
            categorized["pending"].append(obs)

    return categorized


def _get_observer_time_series(request: Request, observer: Observer, days: int) -> dict:
    """
    Get weekly time series data for a specific observer's observations.

    If days=0, returns all observations (lifetime).
    """
    stmt = select(
        Observation.created,
        Observation.actions,
        Observation.related_id,  # type: ignore[attr-defined]
    ).where(
        Observation.observer_id == observer.id,  # type: ignore[attr-defined]
        Observation.kind == "is_malware",
    )

    if days > 0:
        cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=days)
        stmt = stmt.where(Observation.created >= cutoff_date)

    stmt = stmt.order_by(Observation.created.asc())
    observations = request.db.execute(stmt).all()

    return _aggregate_weekly_time_series(observations)


@view_config(
    route_name="admin.observers.reputation",
    renderer="warehouse.admin:templates/admin/observers/reputation.html",
    permission=Permissions.AdminObservationsRead,
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def observer_reputation_dashboard(request: Request):
    """Display the Observer reputation dashboard with statistics and charts."""
    days = _parse_days_param(request)

    # Single query for all observations - used by both stats and time series
    observations = _get_malware_observations(request, days)

    observer_stats = _get_observer_stats(request, observations)
    time_series = _aggregate_weekly_time_series(observations)

    # Calculate summary stats from already-computed observer stats
    total_observations = sum(s["total_observations"] for s in observer_stats)
    total_true_positives = sum(s["true_positives"] for s in observer_stats)
    total_false_positives = sum(s["false_positives"] for s in observer_stats)
    total_pending = sum(s["pending"] for s in observer_stats)

    resolved = total_true_positives + total_false_positives
    overall_accuracy = (
        round((total_true_positives / resolved) * 100, 1) if resolved > 0 else None
    )

    return {
        "days": days,
        "observer_stats": observer_stats,
        "time_series": time_series,
        "summary": {
            "total_observations": total_observations,
            "total_true_positives": total_true_positives,
            "total_false_positives": total_false_positives,
            "total_pending": total_pending,
            "overall_accuracy": overall_accuracy,
            "observer_count": len(observer_stats),
        },
    }


@view_config(
    route_name="admin.observers.detail",
    renderer="warehouse.admin:templates/admin/observers/detail.html",
    permission=Permissions.AdminObservationsRead,
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def observer_detail(request: Request):
    """Display detailed observation history for a specific observer."""
    observer_id = request.matchdict.get("observer_id")
    if not observer_id:
        raise HTTPNotFound("Observer not found")

    observer = request.db.get(Observer, observer_id)
    if not observer:
        raise HTTPNotFound("Observer not found")

    days = _parse_days_param(request, allowed=ALLOWED_DAYS_DETAIL)
    categorized = _get_observer_detail_stats(request, observer, days)
    time_series = _get_observer_time_series(request, observer, days)

    # Calculate stats from categorized observations
    true_pos_count = len(categorized["true_positives"])
    false_pos_count = len(categorized["false_positives"])
    pending_count = len(categorized["pending"])
    total = true_pos_count + false_pos_count + pending_count
    resolved = true_pos_count + false_pos_count
    accuracy = round((true_pos_count / resolved) * 100, 1) if resolved > 0 else None
    score = (true_pos_count * 2) - false_pos_count

    return {
        "observer": observer,
        "username": observer.parent.username if observer.parent else None,
        "user_id": observer.parent.id if observer.parent else None,
        "days": days,
        "observations": categorized,
        "time_series": time_series,
        "stats": {
            "total": total,
            "true_positives": true_pos_count,
            "false_positives": false_pos_count,
            "pending": pending_count,
            "accuracy": accuracy,
            "score": score,
        },
    }
