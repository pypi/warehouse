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

import pretend
import pytest

from zope.interface.verify import verifyClass

from warehouse.subscriptions import services
from warehouse.subscriptions.interfaces import IBillingService, ISubscriptionService
from warehouse.subscriptions.services import (
    GenericBillingService,
    LocalBillingService,
    StripeBillingService,
)


class TestStripeBillingService:
    def test_verify_service(self):
        assert verifyClass(IBillingService, StripeBillingService)

    def test_basic_init(self):
        api = pretend.stub()

        billing_service = StripeBillingService(
            api=api,
            publishable_key="secret_to_everybody",
            webhook_secret="keep_it_secret_keep_it_safe",
        )

        assert billing_service.api is api
        assert billing_service.publishable_key == "secret_to_everybody"
        assert billing_service.webhook_secret == "keep_it_secret_keep_it_safe"

    def test_create_service(self):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://localhost:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = StripeBillingService.create_service(None, request)
        # Assert api_base isn't overwritten with mock service even if we try
        assert not billing_service.api.api_base == "http://localhost:12111"
        assert billing_service.api.api_key == "sk_test_123"
        assert billing_service.publishable_key == "pk_test_123"
        assert billing_service.webhook_secret == "whsec_123"

    # # NOTE: This puppy will work with your own stripe developer secret key
    # #       However, I will be deleting this as it's unneeded and will be
    # #       covered in the LocalBillingService test below
    # def test_get_checkout_session(self):
    #     request = pretend.stub(
    #         registry=pretend.stub(
    #             settings={
    #                 "subscription.secret_key": "sk_test_123",  # Enter your key
    #                 "subscription.publishable_key": "pk_test_123",
    #                 "subscription.webhook_key": "whsec_123",
    #             }
    #         )
    #     )
    #     billing_service = StripeBillingService.create_service(None, request)

    #     random_session = billing_service.api.checkout.Session.list(limit=1)

    #     assert random_session.data[0].object == "checkout.session"

    #     retrieved_session = billing_service.get_checkout_session(
    #         random_session.data[0].id
    #     )

    #     assert retrieved_session.id == random_session.data[0].id


class TestLocalBillingService:
    def test_verify_service(self):
        assert verifyClass(IBillingService, LocalBillingService)

    def test_basic_init(self):
        api = pretend.stub()

        billing_service = LocalBillingService(
            api=api,
            publishable_key="secret_to_everybody",
            webhook_secret="keep_it_secret_keep_it_safe",
        )

        assert billing_service.api is api
        assert billing_service.publishable_key == "secret_to_everybody"
        assert billing_service.webhook_secret == "keep_it_secret_keep_it_safe"

    def test_create_service(self):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "subscription.api_base": "http://localhost:12111",
                    "subscription.secret_key": "sk_test_123",
                    "subscription.publishable_key": "pk_test_123",
                    "subscription.webhook_key": "whsec_123",
                }
            )
        )
        billing_service = LocalBillingService.create_service(None, request)
        assert billing_service.api.api_base == "http://localhost:12111"
        assert billing_service.api.api_key == "sk_test_123"
        assert billing_service.publishable_key == "pk_test_123"
        assert billing_service.webhook_secret == "whsec_123"

    # TODO: UNCOMMENT THIS FUNCTION TO HIT THE MOCK-STRIPE API/DOCKER CONTAINER
    # def test_get_checkout_session(self):
    #     request = pretend.stub(
    #         registry=pretend.stub(
    #             settings={
    #                 "subscription.api_base": "http://localhost:12111",
    #                 "subscription.secret_key": "sk_test_123",
    #                 "subscription.publishable_key": "pk_test_123",
    #                 "subscription.webhook_key": "whsec_123",
    #             }
    #         )
    #     )
    #     billing_service = StripeBillingService.create_service(None, request)

    #     assert billing_service.api.api_key == "sk_test_123"

    #     billing_service.api.verify_ssl_certs = False

    #     random_session = billing_service.api.checkout.Session.list(limit=1)

    #     assert random_session.data[0].object == "checkout.session"

    #     retrieved_session = billing_service.get_checkout_session(
    #         random_session.data[0].id
    #     )

    #     assert retrieved_session.id == random_session.data[0].id


class TestGenericBillingService:
    def test_basic_init(self):
        api = pretend.stub()

        billing_service = GenericBillingService(
            api=api,
            publishable_key="secret_to_everybody",
            webhook_secret="keep_it_secret_keep_it_safe",
        )

        assert billing_service.api is api
        assert billing_service.publishable_key == "secret_to_everybody"
        assert billing_service.webhook_secret == "keep_it_secret_keep_it_safe"

    def test_notimplementederror(self):
        with pytest.raises(NotImplementedError):
            GenericBillingService.create_service(pretend.stub(), pretend.stub())


def test_subscription_factory():
    db = pretend.stub()
    context = pretend.stub()
    request = pretend.stub(db=db)

    service = services.subscription_factory(context, request)
    assert service.db is db


class TestSubscriptionService:
    def test_verify_service(self):
        assert verifyClass(ISubscriptionService, services.SubscriptionService)

    def test_service_creation(self, remote_addr):
        session = pretend.stub()
        service = services.SubscriptionService(session)

        assert service.db is session

    # TODO: MORE TESTS!!!
