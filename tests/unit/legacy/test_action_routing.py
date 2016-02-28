# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pretend
import pytest

from warehouse.legacy import action_routing


@pytest.mark.parametrize(
    ("action", "params", "expected"),
    [
        ("foo", {":action": "foo"}, True),
        ("foo", {":action": "bar"}, False),
        ("bar", {}, False),
    ],
)
def test_pypi_action(action, params, expected):
    res = action_routing.pypi_action(action)({}, pretend.stub(params=params))
    assert res == expected


def test_add_pypi_action_route(monkeypatch):
    pred = pretend.stub()
    pypi_action = pretend.call_recorder(lambda name: pred)
    monkeypatch.setattr(action_routing, "pypi_action", pypi_action)

    config = pretend.stub(
        add_route=pretend.call_recorder(lambda *a, **k: None),
    )

    action_routing.add_pypi_action_route(config, "the name", "the action")

    assert config.add_route.calls == [
        pretend.call("the name", "/pypi", custom_predicates=[pred]),
    ]


def test_includeme():
    config = pretend.stub(
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
