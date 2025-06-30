# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse import subscriptions
from warehouse.subscriptions.interfaces import IBillingService, ISubscriptionService
from warehouse.subscriptions.services import subscription_factory


def test_includeme():
    billing_class = pretend.stub(
        create_service=pretend.call_recorder(lambda *a, **kw: pretend.stub())
    )

    settings = dict()

    config = pretend.stub(
        maybe_dotted=lambda dotted: billing_class,
        register_service_factory=pretend.call_recorder(
            lambda factory, iface, name=None: None
        ),
        registry=pretend.stub(
            settings={
                "billing.backend": "hand.some",
            }
        ),
        get_settings=lambda: settings,
    )

    subscriptions.includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(subscription_factory, ISubscriptionService),
        pretend.call(billing_class.create_service, IBillingService),
    ]
