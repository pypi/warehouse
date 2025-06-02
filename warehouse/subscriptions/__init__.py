# SPDX-License-Identifier: Apache-2.0

from warehouse.subscriptions.interfaces import IBillingService, ISubscriptionService
from warehouse.subscriptions.services import subscription_factory


def includeme(config):
    # Register our subscription service
    config.register_service_factory(subscription_factory, ISubscriptionService)
    # Register whatever payment service provider has been configured
    billing_class = config.maybe_dotted(config.registry.settings["billing.backend"])
    config.register_service_factory(billing_class.create_service, IBillingService)
