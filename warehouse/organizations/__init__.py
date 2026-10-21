# SPDX-License-Identifier: Apache-2.0

from celery.schedules import crontab

from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.services import database_organization_factory
from warehouse.organizations.tasks import (
    delete_declined_organization_applications,
    reconcile_stripe_status,
    schedule_unpaid_organization_deactivations,
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
    # Scheduled an hour before update_organziation_subscription_usage_record
    # (hour=0) so usage is usually reported against Stripe-synced status. Best
    # effort only: nothing chains the two, so if reconcile exhausts its retries
    # the usage task still runs against whatever status is stored.
    config.add_periodic_task(crontab(minute=0, hour=23), reconcile_stripe_status)
    config.add_periodic_task(
        crontab(minute=0, hour=0), update_organziation_subscription_usage_record
    )
    # Status reconciliation is best effort; notices are dispatched after this commits.
    config.add_periodic_task(
        crontab(minute=0, hour=1), schedule_unpaid_organization_deactivations
    )
