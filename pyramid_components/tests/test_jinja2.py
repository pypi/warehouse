# SPDX-License-Identifier: Apache-2.0
import pytest

from pyramid_components.component import Component

from pyramid_components import registry as registry_module


@pytest.fixture
def widget(isolate_registry):
    @registry_module.register("widget")
    class Widget(Component):
        template = "widget/widget.html"

        class Props:
            label: str
            href: str | None = None

    return Widget


def test_tag_renders_component_with_kwargs(widget, make_env):
    env = make_env({"widget/widget.html": "<span>{{ label }}</span>"})
    template = env.from_string('{% component "widget", label="Hello" %}')

    assert template.render() == "<span>Hello</span>"


def test_tag_evaluates_kwargs_in_parent_context(widget, make_env):
    env = make_env({"widget/widget.html": '<a href="{{ href }}">{{ label }}</a>'})
    template = env.from_string('{% component "widget", label=greeting, href=url %}')

    rendered = template.render(greeting="Hi", url="/x")

    assert rendered == '<a href="/x">Hi</a>'


def test_tag_output_is_autoescape_safe(widget, make_env):
    env = make_env({"widget/widget.html": "<span>{{ label }}</span>"})
    # Component output must not be double-escaped when emitted into the page.
    template = env.from_string('<div>{% component "widget", label="A&B" %}</div>')

    assert template.render() == "<div><span>A&amp;B</span></div>"


def test_tag_with_no_kwargs(make_env, isolate_registry):
    @registry_module.register("bare")
    class Bare(Component):
        template = "bare/bare.html"

    env = make_env({"bare/bare.html": "<hr>"})
    template = env.from_string('{% component "bare" %}')

    assert template.render() == "<hr>"


def test_tag_allows_prop_named_name(make_env, isolate_registry):
    """A prop named ``name`` must not collide with _render's own parameter."""

    @registry_module.register("greeting")
    class Greeting(Component):
        template = "greeting/greeting.html"

        class Props:
            name: str

    env = make_env({"greeting/greeting.html": "<p>Hello {{ name }}</p>"})
    template = env.from_string('{% component "greeting", name="Mike" %}')

    assert template.render() == "<p>Hello Mike</p>"
