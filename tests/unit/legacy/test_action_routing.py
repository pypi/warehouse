# SPDX-License-Identifier: Apache-2.0

from pyramid.config import Configurator

from warehouse.legacy import action_routing


def test_add_pypi_action_route(mocker):
    config = mocker.Mock(spec=Configurator)

    action_routing.add_pypi_action_route(config, "the name", "the action")

    config.add_route.assert_called_once_with(
        "the name", "/pypi", pypi_action="the action"
    )


def test_includeme(mocker):
    config = mocker.Mock(spec=Configurator)

    action_routing.includeme(config)

    assert config.add_directive.call_args_list == [
        mocker.call(
            "add_pypi_action_route",
            action_routing.add_pypi_action_route,
            action_wrap=False,
        ),
        mocker.call(
            "add_pypi_action_redirect",
            action_routing.add_pypi_action_redirect,
            action_wrap=False,
        ),
    ]
