# SPDX-License-Identifier: Apache-2.0

import pretend

from celery.schedules import crontab

from warehouse import gating
from warehouse.gating.interfaces import IGateService
from warehouse.gating.services import gate_service_factory, register_gate_policy
from warehouse.gating.tasks import compute_gating_metrics, resolve_timed_out_gates


class _StubPolicy:
    kind = "stub"
    timeout = None
    timeout_status = None

    def applies(self, release, request):
        return True


def _config(settings=None):
    return pretend.stub(
        registry=pretend.stub(settings=settings or {}),
        add_directive=pretend.call_recorder(lambda *a, **kw: None),
        register_service_factory=pretend.call_recorder(lambda *a, **kw: None),
        register_gate_policy=pretend.call_recorder(lambda *a, **kw: None),
        add_periodic_task=pretend.call_recorder(lambda *a, **kw: None),
    )


class TestIncludeMe:
    def test_registers_directive_service_and_tasks(self):
        config = _config()

        gating.includeme(config)

        assert config.add_directive.calls == [
            pretend.call("register_gate_policy", register_gate_policy)
        ]
        assert config.register_service_factory.calls == [
            pretend.call(gate_service_factory, IGateService)
        ]
        assert config.add_periodic_task.calls == [
            pretend.call(crontab(minute="*/1"), resolve_timed_out_gates),
            pretend.call(crontab(minute="*/5"), compute_gating_metrics),
        ]

    def test_registers_no_gates_of_its_own(self):
        """Registering one here would make every deployment inherit a hold."""
        config = _config()

        gating.includeme(config)

        assert config.register_gate_policy.calls == []


class TestGateServiceFactory:
    def test_builds_a_service_with_registry_policies(self, db_request):
        policy = _StubPolicy()
        db_request.registry["gating.policies"] = [policy]

        service = gate_service_factory(None, db_request)

        assert service.db is db_request.db
        assert service.policies() == [policy]

    def test_builds_a_service_with_no_policies(self, db_request):
        service = gate_service_factory(None, db_request)

        assert service.policies() == []
