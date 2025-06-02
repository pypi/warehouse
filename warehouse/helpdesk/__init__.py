# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing

from .interfaces import IAdminNotificationService, IHelpDeskService

if typing.TYPE_CHECKING:
    from pyramid.config import Configurator


def includeme(config: Configurator) -> None:
    helpdesk_class = config.maybe_dotted(config.registry.settings["helpdesk.backend"])
    notification_class = config.maybe_dotted(
        config.registry.settings["helpdesk.notification_backend"]
    )

    config.register_service_factory(helpdesk_class.create_service, IHelpDeskService)
    config.register_service_factory(
        notification_class.create_service, IAdminNotificationService
    )
