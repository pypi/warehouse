# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse.legacy import action_routing


def test_add_pypi_action_route():
    config = pretend.stub(add_route=pretend.call_recorder(lambda *a, **k: None))

    action_routing.add_pypi_action_route(config, "the name", "the action")

    assert config.add_route.calls == [
        pretend.call("the name", "/pypi", pypi_action="the action")
    ]


def test_includeme():
    config = pretend.stub(
        add_route_predicate=pretend.call_recorder(lambda name, pred: None),
        add_directive=pretend.call_recorder(lambda name, f, action_wrap: None),
    )

    action_routing.includeme(config)

    assert config.add_directive.calls == [
        pretend.call(
            "add_pypi_action_route",
            action_routing.add_pypi_action_route,
            action_wrap=False,
        ),
        pretend.call(
            "add_pypi_action_redirect",
            action_routing.add_pypi_action_redirect,
            action_wrap=False,
        ),
    ]
