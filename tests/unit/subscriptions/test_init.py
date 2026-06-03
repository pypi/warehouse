# SPDX-License-Identifier: Apache-2.0

from warehouse import subscriptions
from warehouse.subscriptions.interfaces import IBillingService, ISubscriptionService
from warehouse.subscriptions.services import subscription_factory


def test_includeme(mocker):
    billing_class = mocker.Mock(spec=["create_service"])
    config = mocker.Mock(
        spec=["maybe_dotted", "register_service_factory", "registry", "get_settings"]
    )
    config.maybe_dotted.return_value = billing_class
    config.registry.settings = {"billing.backend": "hand.some"}
    config.get_settings.return_value = {}

    subscriptions.includeme(config)

    assert config.register_service_factory.call_args_list == [
        mocker.call(subscription_factory, ISubscriptionService),
        mocker.call(billing_class.create_service, IBillingService),
    ]
