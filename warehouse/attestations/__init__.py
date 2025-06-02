# SPDX-License-Identifier: Apache-2.0

from warehouse.attestations.interfaces import IIntegrityService


def includeme(config):
    integrity_service_class = config.maybe_dotted(
        config.registry.settings["integrity.backend"]
    )
    config.register_service_factory(
        integrity_service_class.create_service, IIntegrityService
    )
