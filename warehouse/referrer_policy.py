# SPDX-License-Identifier: Apache-2.0


def referrer_policy_tween_factory(handler, registry):
    def referrer_policy_tween(request):
        response = handler(request)

        response.headers["Referrer-Policy"] = "origin-when-cross-origin"

        return response

    return referrer_policy_tween


def includeme(config):
    config.add_tween("warehouse.referrer_policy.referrer_policy_tween_factory")
