# SPDX-License-Identifier: Apache-2.0

import warehouse.legacy.api.xmlrpc.views  # noqa


def includeme(config):
    ratelimit_string = config.registry.settings.get(
        "warehouse.xmlrpc.client.ratelimit_string"
    )
    config.register_rate_limiter(ratelimit_string, "xmlrpc.client")
