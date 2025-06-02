# SPDX-License-Identifier: Apache-2.0

import b2sdk.v2


def b2_api_factory(context, request):
    b2_api = b2sdk.v2.B2Api(b2sdk.v2.InMemoryAccountInfo())
    b2_api.authorize_account(
        "production",
        request.registry.settings["b2.application_key_id"],
        request.registry.settings["b2.application_key"],
    )
    return b2_api


def includeme(config):
    config.register_service_factory(b2_api_factory, name="b2.api")
