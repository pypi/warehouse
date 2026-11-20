# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing

import structlog

from sqlalchemy import func, select
from zope.interface import implementer

from warehouse.gating.interfaces import IGatePolicy, IGateService
from warehouse.gating.models import (
    GATE_KIND_MAX_LENGTH,
    GateStatus,
    ReleaseGate,
)

if typing.TYPE_CHECKING:
    from pyramid.request import Request

    from warehouse.packaging.models import Release

logger = structlog.get_logger(__name__)

# Policies are process-wide and registered at configuration time, while the
# service itself is per-request because it needs the request's DB session.
POLICY_REGISTRY_KEY = "gating.policies"


@implementer(IGateService)
class GateService:
    def __init__(self, db_session, policies=None):
        self.db = db_session
        self._policies: dict[str, IGatePolicy] = {}
        for policy in policies or []:
            self.register_policy(policy)

    def register_policy(self, policy: IGatePolicy) -> None:
        _check_kind(policy.kind)
        if policy.kind in self._policies:
            raise ValueError(f"A policy for {policy.kind!r} is already registered")
        self._policies[policy.kind] = policy

    def policies(self) -> list[IGatePolicy]:
        return list(self._policies.values())

    def policy_for(self, kind: str) -> IGatePolicy | None:
        return self._policies.get(kind)

    def open_gates(self, release: Release, request: Request) -> list[ReleaseGate]:
        opened = []

        existing = {gate.kind: gate for gate in self._gates_for(release)}

        for policy in self._policies.values():
            if not policy.applies(release, request):
                continue

            gate = existing.get(policy.kind)
            if gate is None:
                gate = ReleaseGate(
                    release=release,
                    kind=policy.kind,
                    status=GateStatus.Pending,
                    note=f"Awaiting {policy.kind}",
                )
                self.db.add(gate)
            else:
                # The earlier decision was about the files that existed then,
                # so the gate is reopened rather than reused.
                gate.status = GateStatus.Pending
                gate.resolved = None
                gate.resolved_by = None
                gate.details = None
                gate.note = f"Reopened, awaiting {policy.kind}"

            opened.append(gate)

        if opened:
            self._set_gated(release, True)

        logger.info(
            "release_gates_opened",
            release_id=str(release.id),
            kinds=[gate.kind for gate in opened],
        )

        return opened

    def resolve(
        self,
        release: Release,
        kind: str,
        status: GateStatus,
        *,
        note: str | None = None,
        resolved_by: str | None = None,
        details: dict | None = None,
    ) -> ReleaseGate | None:
        gate = self.db.scalars(
            select(ReleaseGate).where(
                ReleaseGate.release_id == release.id, ReleaseGate.kind == kind
            )
        ).one_or_none()

        if gate is None:
            logger.warning(
                "release_gate_resolve_missing",
                release_id=str(release.id),
                kind=kind,
            )
            return None

        gate.status = status
        gate.note = note
        gate.resolved_by = resolved_by
        gate.details = details
        gate.resolved = None if status == GateStatus.Pending else _now(self.db)

        logger.info(
            "release_gate_resolved",
            release_id=str(release.id),
            kind=kind,
            status=str(status),
            resolved_by=resolved_by,
        )

        self._recompute(release)

        return gate

    def blocking_gates(self, release: Release) -> list[ReleaseGate]:
        return [gate for gate in self._gates_for(release) if gate.blocking]

    def is_gated(self, release: Release) -> bool:
        return bool(self.blocking_gates(release))

    def _gates_for(self, release: Release) -> list[ReleaseGate]:
        return list(
            self.db.scalars(
                select(ReleaseGate).where(ReleaseGate.release_id == release.id)
            ).all()
        )

    def _recompute(self, release: Release) -> None:
        """Bring `Release.gated` back in line with the release's gates."""
        self._set_gated(release, self.is_gated(release))

    def _set_gated(self, release: Release, gated: bool) -> None:
        if release.gated == gated:
            return

        release.gated = gated

        # No explicit CDN purge: `Release` carries origin cache purge keys, so
        # mutating it marks it dirty and the purge of the index and API pages is
        # queued at commit. The files themselves stay in the cache bucket either
        # way; gating only changes whether the release is listed.


def _now(db_session):
    """Database `now()`, so gate timestamps share the transaction's clock."""
    return db_session.scalar(select(func.now()))


def _check_kind(kind) -> None:
    """
    Reject a kind the column cannot hold.

    Checked at registration, which happens at startup, so a malformed policy
    fails the deployment rather than an upload.
    """
    if not isinstance(kind, str) or not kind:
        raise ValueError(f"A gate policy kind must be a non-empty string, not {kind!r}")
    if len(kind) > GATE_KIND_MAX_LENGTH:
        raise ValueError(
            f"Gate policy kind {kind!r} is longer than "
            f"{GATE_KIND_MAX_LENGTH} characters"
        )


def gate_service_factory(context, request) -> GateService:
    return GateService(
        request.db,
        policies=request.registry.get(POLICY_REGISTRY_KEY, []),
    )


def register_gate_policy(config, policy) -> None:
    """
    Pyramid directive: `config.register_gate_policy(policy)`.

    The supported way to add a gate. The mechanism ships with none of its own.
    """
    _check_kind(policy.kind)

    policies = config.registry.setdefault(POLICY_REGISTRY_KEY, [])

    if any(existing.kind == policy.kind for existing in policies):
        raise ValueError(f"A policy for {policy.kind!r} is already registered")

    policies.append(policy)
