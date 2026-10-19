# SPDX-License-Identifier: Apache-2.0

from warehouse.forklift import action_routing


def test_add_legacy_action_route(mocker):
    config = mocker.Mock(spec=["add_route"])

    action_routing.add_legacy_action_route(config, "the name", "the action")

    config.add_route.assert_called_once_with(
        "the name", "/legacy/", pypi_action="the action"
    )


def test_includeme(mocker):
    config = mocker.Mock(spec=["add_directive"])

    action_routing.includeme(config)

    config.add_directive.assert_called_once_with(
        "add_legacy_action_route",
        action_routing.add_legacy_action_route,
        action_wrap=False,
    )
