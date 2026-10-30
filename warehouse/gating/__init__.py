# SPDX-License-Identifier: Apache-2.0

"""
Release gating: a reusable hold on a `Release`.

Only the mechanism; it registers no gates. See
`docs/dev/development/release-gating.md` for how to add one.
"""

from __future__ import annotations

from celery.schedules import crontab

from warehouse.gating.interfaces import IGateService
from warehouse.gating.services import (
    gate_service_factory,
    register_gate_policy,
)
from warehouse.gating.tasks import compute_gating_metrics, resolve_timed_out_gates


def includeme(config):
    config.add_directive("register_gate_policy", register_gate_policy)
    config.register_service_factory(gate_service_factory, IGateService)

    # Runs often relative to the shortest policy timeout. Gate rows outlive the
    # policy that created them, so this matters even with nothing registered.
    config.add_periodic_task(crontab(minute="*/1"), resolve_timed_out_gates)
    config.add_periodic_task(crontab(minute="*/5"), compute_gating_metrics)
