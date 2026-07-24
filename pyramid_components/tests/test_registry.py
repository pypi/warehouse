# SPDX-License-Identifier: Apache-2.0
import jinja2
import pytest

from markupsafe import Markup
from pyramid_components.component import Component

from pyramid_components import registry as registry_module


def test_register_and_get():
    @registry_module.register("widget")
    class Widget(Component):
        template = "widget.html"

    assert registry_module.get("widget") is Widget


def test_register_duplicate_raises():
    @registry_module.register("dup")
    class A(Component):
        template = "a.html"

    with pytest.raises(registry_module.ComponentAlreadyRegisteredError):

        @registry_module.register("dup")
        class B(Component):
            template = "b.html"


def test_register_same_class_again_replaces():
    """Re-registering the same class (e.g. a module reload) is not an error."""

    @registry_module.register("reloaded")
    class Widget(Component):
        template = "widget.html"

    replacement = registry_module.register("reloaded")(Widget)

    assert replacement is Widget
    assert registry_module.get("reloaded") is Widget


def test_get_missing_raises():
    with pytest.raises(registry_module.ComponentNotRegisteredError):
        registry_module.get("nope")


def test_render_binds_props_and_returns_markup():
    @registry_module.register("greeting")
    class Greeting(Component):
        template = "greeting.html"

        class Props:
            name: str

    env = jinja2.Environment(
        autoescape=True,
        loader=jinja2.DictLoader({"greeting.html": "<p>Hello {{ name }}</p>"}),
    )

    result = registry_module.render("greeting", env, name="<b>")

    assert isinstance(result, Markup)
    assert result == "<p>Hello &lt;b&gt;</p>"


def test_render_unknown_component_raises():
    env = jinja2.Environment(autoescape=True, loader=jinja2.DictLoader({}))
    with pytest.raises(registry_module.ComponentNotRegisteredError):
        registry_module.render("ghost", env)


def test_render_without_autoescape_is_not_marked_safe():
    """Unescaped output must not bypass an escaping parent template."""

    @registry_module.register("raw")
    class Raw(Component):
        template = "raw.html"

        class Props:
            label: str

    env = jinja2.Environment(
        autoescape=False,  # noqa: S701 -- the non-autoescaping case is under test
        loader=jinja2.DictLoader({"raw.html": "<p>{{ label }}</p>"}),
    )

    result = registry_module.render("raw", env, label="<script>")

    assert not isinstance(result, Markup)
    assert result == "<p><script></p>"


def test_render_with_selective_autoescape_checks_component_template():
    """autoescape may be a per-template-name callable (jinja2.select_autoescape)."""

    @registry_module.register("selective")
    class Selective(Component):
        template = "selective.html"

        class Props:
            label: str

    env = jinja2.Environment(
        autoescape=jinja2.select_autoescape(["html"]),
        loader=jinja2.DictLoader({"selective.html": "<p>{{ label }}</p>"}),
    )

    result = registry_module.render("selective", env, label="<b>")

    assert isinstance(result, Markup)
    assert result == "<p>&lt;b&gt;</p>"
