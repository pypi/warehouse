# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse import banners


def test_includeme():
    config = pretend.stub(
        get_settings=lambda: {"warehouse.domain": "pypi"},
        add_route=pretend.call_recorder(lambda name, route, domain: None),
    )

    banners.includeme(config)

    assert config.add_route.calls == [
        pretend.call(
            "includes.db-banners",
            "/_includes/unauthed/notification-banners/",
            domain="pypi",
        ),
    ]
