# SPDX-License-Identifier: Apache-2.0

import pretend

from celery.schedules import crontab

from warehouse import organizations
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.services import database_organization_factory
from warehouse.organizations.tasks import (
    delete_declined_organization_applications,
    update_organization_invitation_status,
    update_organziation_subscription_usage_record,
)


def test_includeme():
    config = pretend.stub(
        register_service_factory=pretend.call_recorder(
            lambda factory, iface, name=None: None
        ),
        add_periodic_task=pretend.call_recorder(lambda *a, **kw: None),
    )

    organizations.includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(database_organization_factory, IOrganizationService),
    ]

    assert config.add_periodic_task.calls == [
        pretend.call(crontab(minute="*/5"), update_organization_invitation_status),
        pretend.call(
            crontab(minute=0, hour=0), delete_declined_organization_applications
        ),
        pretend.call(
            crontab(minute=0, hour=0), update_organziation_subscription_usage_record
        ),
    ]
