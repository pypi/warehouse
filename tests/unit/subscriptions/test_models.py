# SPDX-License-Identifier: Apache-2.0

from warehouse.subscriptions.models import StripeSubscriptionStatus

from ...common.db.organizations import (
    OrganizationFactory as DBOrganizationFactory,
    OrganizationStripeCustomerFactory as DBOrganizationStripeCustomerFactory,
)
from ...common.db.subscriptions import (
    StripeCustomerFactory as DBStripeCustomerFactory,
    StripeSubscriptionFactory as DBStripeSubscriptionFactory,
)


class TestStripeSubscription:
    def test_is_restricted(self, db_session):
        organization = DBOrganizationFactory.create()
        stripe_customer = DBStripeCustomerFactory.create()
        DBOrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = DBStripeSubscriptionFactory.create(
            customer=stripe_customer,
            status="past_due",
        )
        assert subscription.is_restricted

    def test_not_is_restricted(self, db_session):
        organization = DBOrganizationFactory.create()
        stripe_customer = DBStripeCustomerFactory.create()
        DBOrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = DBStripeSubscriptionFactory.create(customer=stripe_customer)
        assert not subscription.is_restricted


class TestStripeSubscriptionStatus:
    def test_has_value(self, db_session):
        organization = DBOrganizationFactory.create()
        stripe_customer = DBStripeCustomerFactory.create()
        DBOrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = DBStripeSubscriptionFactory.create(customer=stripe_customer)
        assert StripeSubscriptionStatus.has_value(subscription.status)
        assert not StripeSubscriptionStatus.has_value("invalid_status")
