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


def test_register_different_class_with_same_qualname_raises():
    """A qualname repeats for any class defined inside a function; identity does not."""

    def make():
        class Widget(Component):
            template = "widget.html"

        return Widget

    first, second = make(), make()
    assert (first.__module__, first.__qualname__) == (
        second.__module__,
        second.__qualname__,
    )

    registry_module.register("shared-qualname")(first)

    with pytest.raises(registry_module.ComponentAlreadyRegisteredError):
        registry_module.register("shared-qualname")(second)


def test_render_props_error_names_the_component_and_template():
    """A bare dataclass TypeError names neither, which is all a tracker title shows."""

    @registry_module.register("needs-props")
    class NeedsProps(Component):
        template = "needs.html"

        class Props:
            label: str

    env = jinja2.Environment(
        autoescape=True,
        loader=jinja2.DictLoader({"needs.html": "<p>{{ label }}</p>"}),
    )

    with pytest.raises(registry_module.ComponentPropsError) as excinfo:
        registry_module.render("needs-props", env)

    message = str(excinfo.value)
    assert "'needs-props'" in message
    assert "needs.html" in message
    assert "label" in message


def test_render_raises_on_a_name_that_is_not_a_prop():
    """Component templates see only their props, so an unknown name is drift."""

    @registry_module.register("drifted")
    class Drifted(Component):
        template = "drifted.html"

        class Props:
            label: str

    env = jinja2.Environment(
        autoescape=True,
        loader=jinja2.DictLoader({"drifted.html": "<p>{{ heading }}</p>"}),
    )

    with pytest.raises(jinja2.UndefinedError, match="'heading' is undefined"):
        registry_module.render("drifted", env, label="x")


def test_render_leaves_the_host_environment_lenient():
    """Only component renders are strict; the app's own templates are unchanged."""

    @registry_module.register("strictly")
    class Strictly(Component):
        template = "strictly.html"

    env = jinja2.Environment(
        autoescape=True,
        loader=jinja2.DictLoader(
            {"strictly.html": "<p>ok</p>", "page.html": "<p>{{ nope }}</p>"}
        ),
    )

    registry_module.render("strictly", env)

    assert env.get_template("page.html").render() == "<p></p>"
    assert env.undefined is jinja2.Undefined


def test_strict_environment_is_memoized_per_environment():
    """The overlay carries its own template cache, so it must not be rebuilt."""
    env = jinja2.Environment(autoescape=True, loader=jinja2.DictLoader({}))

    first = registry_module._strict_environment(env)

    assert registry_module._strict_environment(env) is first
    assert first.undefined is jinja2.StrictUndefined
