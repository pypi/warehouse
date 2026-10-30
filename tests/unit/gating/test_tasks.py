# SPDX-License-Identifier: Apache-2.0

import datetime

import pretend

from sqlalchemy import func, update

from warehouse.gating.models import GateStatus, ReleaseGate
from warehouse.gating.tasks import compute_gating_metrics, resolve_timed_out_gates

from ...common.db.gating import ReleaseGateFactory
from ...common.db.packaging import ReleaseFactory


class _StubPolicy:
    def __init__(self, kind, timeout, timeout_status):
        self.kind = kind
        self.timeout = timeout
        self.timeout_status = timeout_status


def _backdate(db_session, gate, delta):
    """Age a gate on the database's own clock, which is what the sweep compares."""
    db_session.flush()
    db_session.execute(
        update(ReleaseGate)
        .where(ReleaseGate.id == gate.id)
        .values(created=func.now() - delta)
    )
    db_session.refresh(gate)


class TestResolveTimedOutGates:
    def test_leaves_a_fresh_gate_pending(self, db_request, gate_service):
        release = ReleaseFactory.create(gated=True)
        gate = ReleaseGateFactory.create(
            release=release, kind="slow-gate", status=GateStatus.Pending
        )
        gate_service.register_policy(
            _StubPolicy("slow-gate", datetime.timedelta(hours=6), GateStatus.Expired)
        )

        resolve_timed_out_gates(db_request)

        assert gate.status == GateStatus.Pending
        assert release.gated is True

    def test_expires_a_gate_past_its_timeout(self, db_request, gate_service):
        release = ReleaseFactory.create(gated=True)
        gate = ReleaseGateFactory.create(
            release=release, kind="slow-gate", status=GateStatus.Pending
        )
        _backdate(db_request.db, gate, datetime.timedelta(hours=12))
        gate_service.register_policy(
            _StubPolicy("slow-gate", datetime.timedelta(hours=6), GateStatus.Expired)
        )

        resolve_timed_out_gates(db_request)

        # Fails open, but recorded as Expired rather than Passed.
        assert gate.status == GateStatus.Expired
        assert gate.resolved_by == "gating.sweep"
        assert "did not resolve" in gate.note
        assert release.gated is False

    def test_passes_a_delay_gate_once_the_window_elapses(
        self, db_request, gate_service
    ):
        release = ReleaseFactory.create(gated=True)
        gate = ReleaseGateFactory.create(
            release=release, kind="wait-gate", status=GateStatus.Pending
        )
        _backdate(db_request.db, gate, datetime.timedelta(minutes=10))
        gate_service.register_policy(
            _StubPolicy("wait-gate", datetime.timedelta(minutes=5), GateStatus.Passed)
        )

        resolve_timed_out_gates(db_request)

        # Waiting is this policy's whole mechanism, so elapsing is a pass.
        assert gate.status == GateStatus.Passed
        assert "elapsed" in gate.note
        assert release.gated is False

    def test_fail_closed_policy_keeps_withholding(self, db_request, gate_service):
        release = ReleaseFactory.create(gated=True)
        gate = ReleaseGateFactory.create(
            release=release, kind="slow-gate", status=GateStatus.Pending
        )
        _backdate(db_request.db, gate, datetime.timedelta(hours=12))
        gate_service.register_policy(
            _StubPolicy("slow-gate", datetime.timedelta(hours=6), GateStatus.Failed)
        )

        resolve_timed_out_gates(db_request)

        assert gate.status == GateStatus.Failed
        assert release.gated is True

    def test_expires_a_gate_whose_policy_is_gone(self, db_request):
        """A retired gate kind must not withhold its release forever."""
        release = ReleaseFactory.create(gated=True)
        gate = ReleaseGateFactory.create(
            release=release, kind="slow-gate", status=GateStatus.Pending
        )

        # No policy is registered for "slow-gate" on the service.
        resolve_timed_out_gates(db_request)

        assert gate.status == GateStatus.Expired
        assert "No policy is registered" in gate.note
        assert release.gated is False

    def test_ignores_a_policy_with_no_timeout(self, db_request, gate_service):
        release = ReleaseFactory.create(gated=True)
        gate = ReleaseGateFactory.create(
            release=release, kind="slow-gate", status=GateStatus.Pending
        )
        _backdate(db_request.db, gate, datetime.timedelta(days=30))
        gate_service.register_policy(_StubPolicy("slow-gate", None, GateStatus.Expired))

        resolve_timed_out_gates(db_request)

        assert gate.status == GateStatus.Pending
        assert release.gated is True

    def test_skips_already_resolved_gates(self, db_request, gate_service):
        release = ReleaseFactory.create()
        gate = ReleaseGateFactory.create(
            release=release, kind="slow-gate", status=GateStatus.Passed
        )
        _backdate(db_request.db, gate, datetime.timedelta(days=1))
        gate_service.register_policy(
            _StubPolicy("slow-gate", datetime.timedelta(hours=1), GateStatus.Expired)
        )

        resolve_timed_out_gates(db_request)

        assert gate.status == GateStatus.Passed

    def test_emits_a_metric_per_timed_out_gate(self, db_request, gate_service, metrics):
        release = ReleaseFactory.create(gated=True)
        gate = ReleaseGateFactory.create(
            release=release, kind="slow-gate", status=GateStatus.Pending
        )
        _backdate(db_request.db, gate, datetime.timedelta(hours=12))
        gate_service.register_policy(
            _StubPolicy("slow-gate", datetime.timedelta(hours=6), GateStatus.Expired)
        )

        resolve_timed_out_gates(db_request)

        assert (
            pretend.call(
                "warehouse.gating.timed_out",
                tags=["kind:slow-gate", "status:expired"],
            )
            in metrics.increment.calls
        )


class TestComputeGatingMetrics:
    def test_gauges_per_kind_and_status(self, db_request, metrics):
        release = ReleaseFactory.create()
        ReleaseGateFactory.create(
            release=release, kind="slow-gate", status=GateStatus.Pending
        )
        ReleaseGateFactory.create(
            release=release, kind="wait-gate", status=GateStatus.Passed
        )

        compute_gating_metrics(db_request)

        assert (
            pretend.call(
                "warehouse.gating.gates",
                1,
                tags=["kind:slow-gate", "status:pending"],
            )
            in metrics.gauge.calls
        )
        assert (
            pretend.call(
                "warehouse.gating.gates",
                1,
                tags=["kind:wait-gate", "status:passed"],
            )
            in metrics.gauge.calls
        )

    def test_no_gates_emits_nothing(self, db_request, metrics):
        compute_gating_metrics(db_request)

        assert metrics.gauge.calls == []


class TestSweepBatching:
    def test_resolves_many_gates_in_one_pass(self, db_request, gate_service):
        releases = [ReleaseFactory.create(gated=True) for _ in range(5)]
        gates = [
            ReleaseGateFactory.create(
                release=release,
                kind="slow-gate",
                status=GateStatus.Pending,
            )
            for release in releases
        ]
        for gate in gates:
            _backdate(db_request.db, gate, datetime.timedelta(hours=9))

        gate_service.register_policy(
            _StubPolicy("slow-gate", datetime.timedelta(hours=6), GateStatus.Expired)
        )

        resolve_timed_out_gates(db_request)

        assert all(gate.status == GateStatus.Expired for gate in gates)
        assert all(release.gated is False for release in releases)
        assert (
            db_request.db.query(ReleaseGate)
            .filter(ReleaseGate.status == GateStatus.Pending)
            .count()
            == 0
        )
