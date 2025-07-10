# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse.helpdesk import includeme
from warehouse.helpdesk.interfaces import IAdminNotificationService, IHelpDeskService


def test_includeme():
    dummy_klass = pretend.stub(create_service=pretend.stub())
    config = pretend.stub(
        registry=pretend.stub(
            settings={
                "helpdesk.backend": "test.HelpDeskService",
                "helpdesk.notification_backend": "test.NotificationService",
            }
        ),
        maybe_dotted=pretend.call_recorder(lambda n: dummy_klass),
        register_service_factory=pretend.call_recorder(lambda s, i, **kw: None),
    )

    includeme(config)

    assert config.maybe_dotted.calls == [
        pretend.call("test.HelpDeskService"),
        pretend.call("test.NotificationService"),
    ]
    assert config.register_service_factory.calls == [
        pretend.call(dummy_klass.create_service, IHelpDeskService),
        pretend.call(dummy_klass.create_service, IAdminNotificationService),
    ]
