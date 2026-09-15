# SPDX-License-Identifier: Apache-2.0

from celery.schedules import crontab

from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.services import database_organization_factory
from warehouse.organizations.tasks import (
    delete_declined_organization_applications,
    notify_organizations_requiring_subscription,
    update_organization_invitation_status,
    update_organziation_subscription_usage_record,
)


def includeme(config):
    # Register our organization service
    config.register_service_factory(database_organization_factory, IOrganizationService)

    config.add_periodic_task(
        crontab(minute="*/5"), update_organization_invitation_status
    )
    config.add_periodic_task(
        crontab(minute=0, hour=0), delete_declined_organization_applications
    )
    config.add_periodic_task(
        crontab(minute=0, hour=0), update_organziation_subscription_usage_record
    )
    # weekly, but the repeat_send is set to 30days
    config.add_periodic_task(
        crontab(minute=0, hour=0, day_of_week=1),
        notify_organizations_requiring_subscription,
    )
