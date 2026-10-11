# SPDX-License-Identifier: Apache-2.0
import dataclasses

from pyramid_components.component import Component


def test_props_inner_class_becomes_dataclass():
    class Card(Component):
        template = "card.html"

        class Props:
            color: str
            icon: str = "fa-box"

    assert dataclasses.is_dataclass(Card.Props)
    bound = Card.Props(color="bg-info")
    assert bound.color == "bg-info"
    assert bound.icon == "fa-box"


def test_default_get_context_returns_props_dict():
    class Card(Component):
        template = "card.html"

        class Props:
            color: str

    bound = Card.Props(color="bg-info")
    assert Card.get_context(bound) == {"color": "bg-info"}


def test_component_without_props_has_empty_props():
    class Bare(Component):
        template = "bare.html"

    assert dataclasses.is_dataclass(Bare.Props)
    assert Bare.get_context(Bare.Props()) == {}


def test_props_inherited_from_mixin_are_used():
    """A Props class from a non-Component base must not be shadowed by the default."""

    class HasColor:
        class Props:
            color: str

    class Card(Component, HasColor):
        template = "card.html"

    assert dataclasses.is_dataclass(Card.Props)
    assert Card.Props(color="bg-info").color == "bg-info"


def test_subclass_inherits_parent_props():
    class Card(Component):
        template = "card.html"

        class Props:
            color: str

    class Special(Card):
        template = "special.html"

    assert Special.Props is Card.Props
    assert Special.Props(color="bg-info").color == "bg-info"


def test_get_context_can_be_overridden():
    class Card(Component):
        template = "card.html"

        class Props:
            count: int

        @classmethod
        def get_context(cls, props):
            return {"count": props.count, "doubled": props.count * 2}

    assert Card.get_context(Card.Props(count=3)) == {"count": 3, "doubled": 6}
