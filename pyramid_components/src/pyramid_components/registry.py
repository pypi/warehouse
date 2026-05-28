# SPDX-License-Identifier: Apache-2.0
"""Module-level component registry and the single render seam.

All component rendering flows through ``render`` so that a future JS/CSS dependency
manager can hook this one path without changing call sites.
"""

from typing import TYPE_CHECKING

from markupsafe import Markup

if TYPE_CHECKING:
    import jinja2

    from pyramid_components.component import Component


class ComponentError(Exception):
    """Base class for registry errors."""


class ComponentAlreadyRegisteredError(ComponentError):
    """Raised when a name is registered twice."""


class ComponentNotRegisteredError(ComponentError):
    """Raised when an unknown component name is requested."""


_registry: dict[str, type[Component]] = {}


def register(name: str):
    """Class decorator that registers a component under ``name``."""

    def decorator(cls: type[Component]) -> type[Component]:
        existing = _registry.get(name)
        if existing is not None and (existing.__module__, existing.__qualname__) != (
            cls.__module__,
            cls.__qualname__,
        ):
            raise ComponentAlreadyRegisteredError(
                f"A component is already registered as {name!r}"
            )
        # Re-registering the same class (e.g. a module reload during development)
        # replaces the entry instead of raising.
        _registry[name] = cls
        return cls

    return decorator


def get(name: str) -> type[Component]:
    """Return the component class registered under ``name``."""
    try:
        return _registry[name]
    except KeyError:
        raise ComponentNotRegisteredError(
            f"No component is registered as {name!r}"
        ) from None


def render(component_name: str, environment: jinja2.Environment, /, **kwargs) -> str:
    """Bind props, build context, and render the component's template.

    The first two parameters are positional-only so they can never collide with
    a component whose ``Props`` has a field of the same name — e.g.
    ``render("greeting", env, name="Mike")``.
    """
    cls = get(component_name)
    props = cls.Props(**kwargs)
    context = cls.get_context(props)
    template = environment.get_template(cls.template)
    rendered = template.render(context)
    # Mark the output safe only when the environment autoescaped the component's
    # template (autoescape may be a per-template-name callable); otherwise the
    # unescaped output must not bypass the parent template's escaping.
    autoescape = environment.autoescape
    if callable(autoescape):
        autoescape = autoescape(cls.template)
    return Markup(rendered) if autoescape else rendered  # noqa: S704
