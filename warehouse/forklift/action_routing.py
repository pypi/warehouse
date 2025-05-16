# SPDX-License-Identifier: Apache-2.0


def add_legacy_action_route(config, name, action, **kwargs):
    config.add_route(name, "/legacy/", pypi_action=action, **kwargs)


def includeme(config):
    config.add_directive(
        "add_legacy_action_route", add_legacy_action_route, action_wrap=False
    )
