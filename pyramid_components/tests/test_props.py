# SPDX-License-Identifier: Apache-2.0
import dataclasses

import pytest

from pyramid_components import props as props_module


def test_as_props_dataclass_converts_plain_class():
    class Props:
        color: str
        icon: str = "fa-box"

    result = props_module.as_props_dataclass(Props)

    assert dataclasses.is_dataclass(result)
    bound = result(color="bg-info")
    assert bound.color == "bg-info"
    assert bound.icon == "fa-box"


def test_as_props_dataclass_is_idempotent():
    @dataclasses.dataclass
    class Props:
        color: str

    assert props_module.as_props_dataclass(Props) is Props


def test_bound_props_require_mandatory_fields():
    class Props:
        color: str

    cls = props_module.as_props_dataclass(Props)
    with pytest.raises(TypeError):
        cls()


def test_bound_props_reject_unknown_fields():
    class Props:
        color: str

    cls = props_module.as_props_dataclass(Props)
    with pytest.raises(TypeError):
        cls(color="x", bogus="y")


def test_props_to_context_returns_field_dict():
    @dataclasses.dataclass
    class Props:
        color: str
        icon: str = "fa-box"

    assert props_module.props_to_context(Props(color="bg-info")) == {
        "color": "bg-info",
        "icon": "fa-box",
    }


def test_props_to_context_is_shallow():
    """Prop values reach the context as-is: no deep copy, no dataclass flattening."""

    @dataclasses.dataclass
    class Item:
        label: str

    @dataclasses.dataclass
    class Props:
        item: Item
        sublines: list[str]

    item = Item(label="x")
    sublines = ["a", "b"]
    context = props_module.props_to_context(Props(item=item, sublines=sublines))

    assert context["item"] is item
    assert context["sublines"] is sublines
