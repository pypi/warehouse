# SPDX-License-Identifier: Apache-2.0

from unittest import mock

from celery.schedules import crontab

from warehouse import gating
from warehouse.gating.interfaces import IGateService
from warehouse.gating.services import gate_service_factory, register_gate_policy
from warehouse.gating.tasks import compute_gating_metrics, resolve_timed_out_gates


class _StubPolicy:
    kind = "stub"
    timeout = None
    timeout_status = None


def _config(settings=None):
    return mock.Mock(
        registry=mock.Mock(settings=settings or {}),
        add_directive=mock.Mock(),
        register_service_factory=mock.Mock(),
        register_gate_policy=mock.Mock(),
        add_periodic_task=mock.Mock(),
    )


class TestIncludeMe:
    def test_registers_directive_service_and_tasks(self):
        config = _config()

        gating.includeme(config)

        assert config.add_directive.call_args_list == [
            mock.call("register_gate_policy", register_gate_policy)
        ]
        assert config.register_service_factory.call_args_list == [
            mock.call(gate_service_factory, IGateService)
        ]
        assert config.add_periodic_task.call_args_list == [
            mock.call(crontab(minute="*/1"), resolve_timed_out_gates),
            mock.call(crontab(minute="*/5"), compute_gating_metrics),
        ]

    def test_registers_no_gates_of_its_own(self):
        """Registering one here would make every deployment inherit a hold."""
        config = _config()

        gating.includeme(config)

        assert config.register_gate_policy.call_args_list == []


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
