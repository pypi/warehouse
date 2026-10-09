# SPDX-License-Identifier: Apache-2.0

"""
Count 404 responses per client IP.

This is observation only: nothing is blocked while we learn the traffic shape.
Once the limit is tuned, blocking can be enabled here.
"""

import ipaddress
import logging

from secrets import randbelow

from pyramid.tweens import EXCVIEW

from warehouse.metrics import IMetricsService
from warehouse.rate_limiting.headers import record_rate_limit
from warehouse.rate_limiting.interfaces import IRateLimiter

logger = logging.getLogger(__name__)

# Log one in this many over-limit 404s. The metric still counts every one.
EXCEEDED_LOG_SAMPLE = 100


def notfound_ratelimit_tween_factory(handler, registry):
    def notfound_ratelimit_tween(request):
        response = handler(request)
        if response.status_code != 404:
            return response

        # Canonicalize the address so the key matches the admin tooling, which
        # reads it back from the INET column (an uncanonicalized IPv6 string
        # would key a different bucket).
        try:
            client_ip = str(ipaddress.ip_address(request.remote_addr))
        except ValueError, TypeError:
            return response

        metrics = request.find_service(IMetricsService, context=None)
        ratelimiter = request.find_service(
            IRateLimiter, name="notfound.ip", context=None
        )
        allowed = ratelimiter.hit(client_ip)
        record_rate_limit(
            request,
            "notfound",
            ratelimiter,
            identifiers=(client_ip,),
            partition_key="ip",
        )
        metrics.increment("warehouse.ratelimit.hit", tags=["limiter:notfound.ip"])
        if not allowed:
            metrics.increment(
                "warehouse.ratelimit.exceeded", tags=["limiter:notfound.ip"]
            )
            if randbelow(EXCEEDED_LOG_SAMPLE) == 0:
                logger.warning(
                    "404 rate limit exceeded",
                    extra={
                        "remote_addr": request.remote_addr_hashed,
                        "path": request.path,
                    },
                )

        return response

    return notfound_ratelimit_tween


def includeme(config):
    config.register_rate_limiter(
        config.registry.settings.get("warehouse.notfound.ip_ratelimit_string"),
        "notfound.ip",
    )
    # Sit above the exception view so raised and returned 404s look the same,
    # and below the headers tween so the recorded snapshot gets rendered.
    config.add_tween(
        "warehouse.rate_limiting.notfound.notfound_ratelimit_tween_factory",
        over=EXCVIEW,
        under="warehouse.rate_limiting.headers.rate_limit_headers_tween_factory",
    )
