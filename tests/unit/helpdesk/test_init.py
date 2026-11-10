# SPDX-License-Identifier: Apache-2.0

import pytest

from warehouse.helpdesk import includeme
from warehouse.helpdesk.interfaces import IAdminNotificationService, IHelpDeskService
from warehouse.helpdesk.services import (
    ConsoleAdminNotificationService,
    ConsoleHelpDeskService,
    HelpScoutService,
    SlackAdminNotificationService,
)


@pytest.mark.parametrize(
    ("backend", "helpdesk_class", "notification_backend", "notification_class"),
    [
        (
            "warehouse.helpdesk.services.HelpScoutService",
            HelpScoutService,
            "warehouse.helpdesk.services.SlackAdminNotificationService",
            SlackAdminNotificationService,
        ),
        (
            "warehouse.helpdesk.services.ConsoleHelpDeskService",
            ConsoleHelpDeskService,
            "warehouse.helpdesk.services.ConsoleAdminNotificationService",
            ConsoleAdminNotificationService,
        ),
    ],
)
def test_includeme(
    pyramid_config,
    mocker,
    backend,
    helpdesk_class,
    notification_backend,
    notification_class,
):
    pyramid_config.include("pyramid_services")
    pyramid_config.registry.settings.update(
        {
            "helpdesk.backend": backend,
            "helpdesk.notification_backend": notification_backend,
        }
    )
    register_service_factory = mocker.spy(pyramid_config, "register_service_factory")

    includeme(pyramid_config)

    assert register_service_factory.call_args_list == [
        mocker.call(helpdesk_class.create_service, IHelpDeskService),
        mocker.call(notification_class.create_service, IAdminNotificationService),
    ]
