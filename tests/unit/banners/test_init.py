# SPDX-License-Identifier: Apache-2.0

from warehouse import banners


def test_includeme(mocker, pyramid_config):
    pyramid_config.include("warehouse.predicates")
    pyramid_config.registry.settings["warehouse.domain"] = "pypi"
    add_route = mocker.spy(pyramid_config, "add_route")

    banners.includeme(pyramid_config)

    add_route.assert_called_once_with(
        "includes.db-banners",
        "/_includes/unauthed/notification-banners/",
        domain="pypi",
    )
