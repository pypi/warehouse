# SPDX-License-Identifier: Apache-2.0

import factory

from warehouse.gating.models import GateStatus, ReleaseGate

from .base import WarehouseFactory
from .packaging import ReleaseFactory


class ReleaseGateFactory(WarehouseFactory):
    class Meta:
        model = ReleaseGate

    release = factory.SubFactory(ReleaseFactory)
    # A placeholder: warehouse ships no gates, so a test that cares about the
    # kind passes its own.
    kind = "test-gate"
    status = GateStatus.Pending
