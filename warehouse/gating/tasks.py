# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import structlog

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from warehouse import tasks
from warehouse.gating.interfaces import IGateService
from warehouse.gating.models import GateStatus, ReleaseGate
from warehouse.metrics import IMetricsService

logger = structlog.get_logger(__name__)

# Capped so one run cannot hold a long transaction or flood the cache-sync
# queue.
SWEEP_BATCH_SIZE = 500


@tasks.task(ignore_result=True, acks_late=True)
def resolve_timed_out_gates(request):
    """
    Resolve pending gates whose policy timeout has elapsed.

    Stops a gate from holding a release forever when whatever was supposed to
    decide it never does. For a policy whose mechanism is purely a wait, the
    timeout elapsing is itself the decision.
    """
    gate_service = request.find_service(IGateService, context=None)
    metrics = request.find_service(IMetricsService, context=None)

    policies = {policy.kind: policy for policy in gate_service.policies()}
    resolved = 0

    # Compared in SQL rather than Python: `created` is naive and written by the
    # database's own `now()`, so this keeps both sides on one clock and lets the
    # sweep use the index on `created`.
    for kind, policy in policies.items():
        if policy.timeout is None:
            continue

        gates = request.db.scalars(
            select(ReleaseGate)
            .options(joinedload(ReleaseGate.release))
            .where(
                ReleaseGate.status == GateStatus.Pending,
                ReleaseGate.kind == kind,
                ReleaseGate.created < func.now() - policy.timeout,
            )
            .order_by(ReleaseGate.created)
            .limit(SWEEP_BATCH_SIZE)
        ).all()

        status = policy.timeout_status

        for gate in gates:
            gate_service.resolve(
                gate.release,
                gate.kind,
                status,
                note=(
                    f"{policy.kind} window of {policy.timeout} elapsed"
                    if status == GateStatus.Passed
                    else f"{policy.kind} did not resolve within {policy.timeout}"
                ),
                resolved_by="gating.sweep",
            )
            resolved += 1

            metrics.increment(
                "warehouse.gating.timed_out",
                tags=[f"kind:{gate.kind}", f"status:{status}"],
            )

    # A gate whose policy is no longer registered would otherwise withhold its
    # release forever, since nothing is left that could decide it.
    orphaned = request.db.scalars(
        select(ReleaseGate)
        .options(joinedload(ReleaseGate.release))
        .where(ReleaseGate.status == GateStatus.Pending)
        .order_by(ReleaseGate.created)
        .limit(SWEEP_BATCH_SIZE)
    ).all()

    for gate in orphaned:
        if gate.kind in policies:
            continue

        gate_service.resolve(
            gate.release,
            gate.kind,
            GateStatus.Expired,
            note="No policy is registered for this gate kind",
            resolved_by="gating.sweep",
        )
        resolved += 1

        metrics.increment(
            "warehouse.gating.timed_out",
            tags=[f"kind:{gate.kind}", "status:expired"],
        )

    logger.info("gating_sweep_complete", resolved=resolved)


@tasks.task(ignore_result=True, acks_late=True)
def compute_gating_metrics(request):
    """Report how many releases are currently withheld, by gate kind/status."""
    metrics = request.find_service(IMetricsService, context=None)

    counts = request.db.execute(
        select(
            ReleaseGate.kind, ReleaseGate.status, func.count(ReleaseGate.id)
        ).group_by(ReleaseGate.kind, ReleaseGate.status)
    ).all()

    for kind, status, count in counts:
        metrics.gauge(
            "warehouse.gating.gates",
            count,
            tags=[f"kind:{kind}", f"status:{status}"],
        )
