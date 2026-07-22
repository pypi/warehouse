# SPDX-License-Identifier: Apache-2.0

from celery.schedules import crontab

from warehouse import organizations
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.services import database_organization_factory
from warehouse.organizations.tasks import (
    delete_declined_organization_applications,
    notify_organizations_requiring_subscription,
    reconcile_stripe_status,
    update_organization_invitation_status,
    update_organziation_subscription_usage_record,
)


def test_includeme(mocker):
    config = mocker.Mock(spec=["register_service_factory", "add_periodic_task"])

    organizations.includeme(config)

    config.register_service_factory.assert_called_once_with(
        database_organization_factory, IOrganizationService
    )
    assert config.add_periodic_task.call_args_list == [
        mocker.call(crontab(minute="*/5"), update_organization_invitation_status),
        mocker.call(
            crontab(minute=0, hour=0), delete_declined_organization_applications
        ),
        mocker.call(crontab(minute=0, hour=23), reconcile_stripe_status),
        mocker.call(
            crontab(minute=0, hour=0), update_organziation_subscription_usage_record
        ),
        mocker.call(
            crontab(minute=0, hour=0, day_of_week=1),
            notify_organizations_requiring_subscription,
        ),
    ]
