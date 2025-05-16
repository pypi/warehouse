# SPDX-License-Identifier: Apache-2.0

import warehouse.legacy.api.xmlrpc.views  # noqa

from warehouse.rate_limiting import IRateLimiter, RateLimit


def includeme(config):
    ratelimit_string = config.registry.settings.get(
        "warehouse.xmlrpc.client.ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(ratelimit_string), IRateLimiter, name="xmlrpc.client"
    )
