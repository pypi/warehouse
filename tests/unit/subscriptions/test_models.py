# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from warehouse.subscriptions.models import StripeSubscriptionStatus

from ...common.db.organizations import (
    OrganizationFactory as DBOrganizationFactory,
    OrganizationStripeCustomerFactory as DBOrganizationStripeCustomerFactory,
)
from ...common.db.subscriptions import (
    StripeSubscriptionFactory as DBStripeSubscriptionFactory,
)


class TestStripeSubscription:
    def test_is_restricted(self, db_session):
        organization = DBOrganizationFactory.create()
        organization_stripe_customer = DBOrganizationStripeCustomerFactory.create(
            organization=organization
        )
        subscription = DBStripeSubscriptionFactory.create(
            customer_id=organization_stripe_customer.customer_id,
            status="past_due",
        )
        assert subscription.is_restricted

    def test_not_is_restricted(self, db_session):
        organization = DBOrganizationFactory.create()
        organization_stripe_customer = DBOrganizationStripeCustomerFactory.create(
            organization=organization
        )
        subscription = DBStripeSubscriptionFactory.create(
            customer_id=organization_stripe_customer.customer_id
        )
        assert not subscription.is_restricted


class TestStripeSubscriptionStatus:
    def test_has_value(self, db_session):
        organization = DBOrganizationFactory.create()
        organization_stripe_customer = DBOrganizationStripeCustomerFactory.create(
            organization=organization
        )
        subscription = DBStripeSubscriptionFactory.create(
            customer_id=organization_stripe_customer.customer_id
        )
        assert StripeSubscriptionStatus.has_value(subscription.status)
        assert not StripeSubscriptionStatus.has_value("invalid_status")
