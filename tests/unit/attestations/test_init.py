# SPDX-License-Identifier: Apache-2.0

import pytest

from warehouse import attestations
from warehouse.attestations.interfaces import IIntegrityService
from warehouse.attestations.services import IntegrityService, NullIntegrityService


@pytest.mark.parametrize(
    ("backend", "service_class"),
    [
        ("warehouse.attestations.services.IntegrityService", IntegrityService),
        ("warehouse.attestations.services.NullIntegrityService", NullIntegrityService),
    ],
)
def test_includeme(pyramid_config, mocker, backend, service_class):
    pyramid_config.include("pyramid_services")
    pyramid_config.registry.settings["integrity.backend"] = backend
    register_service_factory = mocker.spy(pyramid_config, "register_service_factory")

    attestations.includeme(pyramid_config)

    register_service_factory.assert_called_once_with(
        service_class.create_service, IIntegrityService
    )
