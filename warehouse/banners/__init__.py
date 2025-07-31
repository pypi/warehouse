# SPDX-License-Identifier: Apache-2.0


def includeme(config):
    warehouse = config.get_settings().get("warehouse.domain")

    # route to async render banner messages
    config.add_route(
        "includes.db-banners",
        "/_includes/unauthed/notification-banners/",
        domain=warehouse,
    )
