# SPDX-License-Identifier: Apache-2.0

import datetime

import pytest

from zope.interface.verify import verifyClass, verifyObject

from warehouse.gating.interfaces import IGatePolicy, IGateService
from warehouse.gating.models import (
    BLOCKING_GATE_STATUSES,
    GATE_KIND_MAX_LENGTH,
    GateStatus,
    ReleaseGate,
)
from warehouse.gating.services import GateService, register_gate_policy

from ...common.db.gating import ReleaseGateFactory
from ...common.db.packaging import ReleaseFactory


class _StubPolicy:
    """A minimal `IGatePolicy`; warehouse ships none, so tests supply their own."""

    timeout = datetime.timedelta(hours=1)
    timeout_status = GateStatus.Expired

    def __init__(self, kind="stub", applies=True):
        self.kind = kind
        self._applies = applies

    def applies(self, release, request):
        return self._applies


class TestInterfaces:
    def test_service_verifies(self):
        assert verifyClass(IGateService, GateService)

    def test_a_bare_policy_satisfies_the_extension_point(self):
        """The whole contract a new gate has to meet."""
        assert verifyObject(IGatePolicy, _StubPolicy())


class TestGateStatuses:
    def test_only_pending_and_failed_block(self):
        # A new status must not silently become blocking.
        assert {GateStatus.Pending, GateStatus.Failed} == BLOCKING_GATE_STATUSES

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (GateStatus.Pending, True),
            (GateStatus.Failed, True),
            (GateStatus.Passed, False),
            (GateStatus.Bypassed, False),
            (GateStatus.Expired, False),
        ],
    )
    def test_blocking_property(self, db_session, status, expected):
        gate = ReleaseGateFactory.create(status=status)
        assert gate.blocking is expected


class TestOpenGates:
    def test_no_policies_leaves_release_ungated(self, db_request):
        """The shipped default: with no gate registered, the mechanism is inert."""
        release = ReleaseFactory.create()
        service = GateService(db_request.db, policies=[])

        assert service.open_gates(release, db_request) == []
        assert release.gated is False

    def test_opens_gate_and_withholds_release(self, db_request):
        release = ReleaseFactory.create()
        service = GateService(db_request.db, policies=[_StubPolicy()])

        opened = service.open_gates(release, db_request)

        assert len(opened) == 1
        assert opened[0].kind == "stub"
        assert opened[0].status == GateStatus.Pending
        assert release.gated is True

    def test_skips_policy_that_does_not_apply(self, db_request):
        release = ReleaseFactory.create()
        service = GateService(
            db_request.db, policies=[_StubPolicy(applies=False)]
        )

        assert service.open_gates(release, db_request) == []
        assert release.gated is False

    def test_opens_one_gate_per_registered_policy(self, db_request):
        release = ReleaseFactory.create()
        service = GateService(
            db_request.db,
            policies=[_StubPolicy(kind="first"), _StubPolicy(kind="second")],
        )

        opened = service.open_gates(release, db_request)

        assert {gate.kind for gate in opened} == {"first", "second"}
        assert release.gated is True

    def test_is_idempotent_per_kind(self, db_request):
        release = ReleaseFactory.create()
        service = GateService(db_request.db, policies=[_StubPolicy()])

        first = service.open_gates(release, db_request)
        db_request.db.flush()
        second = service.open_gates(release, db_request)
        db_request.db.flush()

        # The unique constraint on (release_id, kind) forbids a second row.
        assert first[0].id == second[0].id
        assert (
            db_request.db.query(ReleaseGate)
            .filter(ReleaseGate.release_id == release.id)
            .count()
            == 1
        )

    def test_reopens_a_resolved_gate(self, db_request):
        """A file added to a cleared release must re-hold it."""
        release = ReleaseFactory.create()
        service = GateService(db_request.db, policies=[_StubPolicy()])

        service.open_gates(release, db_request)
        db_request.db.flush()
        service.resolve(
            release,
            "stub",
            GateStatus.Passed,
            note="cleared",
            resolved_by="stub",
        )
        assert release.gated is False

        reopened = service.open_gates(release, db_request)

        assert reopened[0].status == GateStatus.Pending
        assert reopened[0].resolved is None
        assert reopened[0].resolved_by is None
        assert release.gated is True


class TestResolve:
    def test_passing_the_only_gate_releases_the_hold(self, db_request):
        release = ReleaseFactory.create()
        service = GateService(db_request.db, policies=[_StubPolicy()])
        service.open_gates(release, db_request)
        db_request.db.flush()

        gate = service.resolve(
            release,
            "stub",
            GateStatus.Passed,
            note="cleared",
            resolved_by="stub",
            details={"anything": ["the", "policy", "likes"]},
        )

        assert gate.status == GateStatus.Passed
        assert gate.resolved is not None
        assert gate.note == "cleared"
        assert gate.resolved_by == "stub"
        # Stored and returned unexamined; the mechanism never reads it.
        assert gate.details == {"anything": ["the", "policy", "likes"]}
        assert release.gated is False

    def test_failing_a_gate_keeps_the_hold(self, db_request):
        release = ReleaseFactory.create()
        service = GateService(db_request.db, policies=[_StubPolicy()])
        service.open_gates(release, db_request)
        db_request.db.flush()

        service.resolve(release, "stub", GateStatus.Failed, note="rejected")

        assert release.gated is True

    def test_one_remaining_pending_gate_keeps_the_hold(self, db_request):
        release = ReleaseFactory.create()
        service = GateService(
            db_request.db,
            policies=[_StubPolicy(kind="first"), _StubPolicy(kind="second")],
        )
        service.open_gates(release, db_request)
        db_request.db.flush()

        service.resolve(release, "first", GateStatus.Passed)

        assert release.gated is True

        service.resolve(release, "second", GateStatus.Passed)

        assert release.gated is False

    def test_resolving_a_missing_gate_is_a_noop(self, db_request):
        release = ReleaseFactory.create()
        service = GateService(db_request.db)

        assert service.resolve(release, "stub", GateStatus.Passed) is None
        assert release.gated is False

    def test_resolving_a_gate_with_no_registered_policy(self, db_request):
        """Resolving is keyed on the gate row, so a retired policy's gates clear."""
        release = ReleaseFactory.create(gated=True)
        ReleaseGateFactory.create(
            release=release, kind="retired", status=GateStatus.Pending
        )
        db_request.db.flush()
        service = GateService(db_request.db)

        gate = service.resolve(release, "retired", GateStatus.Bypassed)

        assert gate.status == GateStatus.Bypassed
        assert release.gated is False


class TestQueries:
    def test_blocking_gates_and_is_gated(self, db_request):
        release = ReleaseFactory.create()
        ReleaseGateFactory.create(
            release=release, kind="blocking", status=GateStatus.Pending
        )
        ReleaseGateFactory.create(
            release=release, kind="cleared", status=GateStatus.Passed
        )
        service = GateService(db_request.db)

        blocking = service.blocking_gates(release)

        assert [gate.kind for gate in blocking] == ["blocking"]
        assert service.is_gated(release) is True

    def test_is_gated_false_with_no_gates(self, db_request):
        release = ReleaseFactory.create()
        service = GateService(db_request.db)

        assert service.is_gated(release) is False


class TestPolicyRegistration:
    def test_register_policy(self):
        policy = _StubPolicy()
        service = GateService(None)

        service.register_policy(policy)

        assert service.policies() == [policy]
        assert service.policy_for("stub") is policy

    def test_policy_for_an_unregistered_kind(self):
        service = GateService(None)

        assert service.policy_for("stub") is None

    def test_duplicate_kind_is_rejected(self):
        service = GateService(None, policies=[_StubPolicy()])

        with pytest.raises(ValueError, match="already registered"):
            service.register_policy(_StubPolicy())

    def test_distinct_kinds_coexist(self):
        service = GateService(
            None,
            policies=[_StubPolicy(kind="first"), _StubPolicy(kind="second")],
        )

        assert [policy.kind for policy in service.policies()] == ["first", "second"]

    def test_directive_registers_on_the_registry(self, pyramid_config):
        policy = _StubPolicy()

        register_gate_policy(pyramid_config, policy)

        assert pyramid_config.registry["gating.policies"] == [policy]

    def test_directive_rejects_a_duplicate_kind(self, pyramid_config):
        register_gate_policy(pyramid_config, _StubPolicy())

        with pytest.raises(ValueError, match="already registered"):
            register_gate_policy(pyramid_config, _StubPolicy())


class TestKindValidation:
    """
    `kind` is a plain string, so the schema does not reject a bad one. These
    checks run at registration, which is startup, so a malformed policy fails
    the deployment rather than an upload.
    """

    @pytest.mark.parametrize("kind", ["", None, 42])
    def test_rejects_a_kind_the_column_cannot_hold(self, kind):
        service = GateService(None)

        with pytest.raises(ValueError, match="non-empty string"):
            service.register_policy(_StubPolicy(kind=kind))

    def test_rejects_an_overlong_kind(self):
        service = GateService(None)

        with pytest.raises(ValueError, match="longer than"):
            service.register_policy(_StubPolicy(kind="x" * (GATE_KIND_MAX_LENGTH + 1)))

    def test_accepts_a_kind_at_the_limit(self):
        service = GateService(None)

        service.register_policy(_StubPolicy(kind="x" * GATE_KIND_MAX_LENGTH))

        assert len(service.policies()) == 1

    def test_directive_validates_too(self, pyramid_config):
        """The directive is the supported entry point, so it cannot be the lax one."""
        with pytest.raises(ValueError, match="non-empty string"):
            register_gate_policy(pyramid_config, _StubPolicy(kind=""))
