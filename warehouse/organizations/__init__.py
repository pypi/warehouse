# SPDX-License-Identifier: Apache-2.0

from celery.schedules import crontab

from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.services import database_organization_factory
from warehouse.organizations.tasks import (
    delete_declined_organization_applications,
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
