# SPDX-License-Identifier: Apache-2.0
"""Module-level component registry and the single render seam.

All component rendering flows through ``render`` so that a future JS/CSS dependency
manager can hook this one path without changing call sites.
"""

from typing import TYPE_CHECKING

from jinja2 import StrictUndefined
from markupsafe import Markup

if TYPE_CHECKING:
    import jinja2

    from pyramid_components.component import Component

# Attribute the strict overlay is memoized under, on the environment itself.
_STRICT_ATTR = "_pyramid_components_strict_environment"


class ComponentError(Exception):
    """Base class for registry errors."""


class ComponentAlreadyRegisteredError(ComponentError):
    """Raised when a name is registered twice."""


class ComponentNotRegisteredError(ComponentError):
    """Raised when an unknown component name is requested."""


class ComponentPropsError(ComponentError):
    """Raised when a component's props cannot be bound from the given kwargs."""


_registry: dict[str, type[Component]] = {}


def register(name: str):
    """Class decorator that registers a component under ``name``."""

    def decorator(cls: type[Component]) -> type[Component]:
        existing = _registry.get(name)
        # Compared by identity: a qualname repeats for any class defined inside
        # a function or a conditional, so comparing names would let two
        # different classes overwrite each other.
        if existing is not None and existing is not cls:
            raise ComponentAlreadyRegisteredError(
                f"A component is already registered as {name!r}: "
                f"{existing.__module__}.{existing.__qualname__}"
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


def _strict_environment(environment: jinja2.Environment) -> jinja2.Environment:
    """Return an overlay of ``environment`` that raises on undefined names.

    A component renders against an isolated context, only what ``get_context``
    returns, so any other name a component template reaches for is drift: a
    renamed prop, or a reach for ``request``. Jinja's lenient default renders
    those empty, which turns a mistyped permission gate into a false branch that
    reports nothing.

    The overlay carries its own template cache, so it is memoized on the
    environment. The app's own environment is left alone.
    """
    overlay = getattr(environment, _STRICT_ATTR, None)
    if overlay is None:
        overlay = environment.overlay(undefined=StrictUndefined)
        setattr(environment, _STRICT_ATTR, overlay)
    return overlay


def render(component_name: str, environment: jinja2.Environment, /, **kwargs) -> str:
    """Bind props, build context, and render the component's template.

    The first two parameters are positional-only so they can never collide with
    a component whose ``Props`` has a field of the same name, e.g.
    ``render("greeting", env, name="Mike")``.
    """
    cls = get(component_name)
    try:
        props = cls.Props(**kwargs)
    except TypeError as exc:
        # A bare dataclass TypeError names `Props.__init__` and calls the props
        # positional, naming neither the component nor its template.
        raise ComponentPropsError(
            f"Cannot bind props for component {component_name!r} "
            f"({cls.template}): {exc}"
        ) from exc
    context = cls.get_context(props)
    template = _strict_environment(environment).get_template(cls.template)
    rendered = template.render(context)
    # Mark the output safe only when the environment autoescaped the component's
    # template (autoescape may be a per-template-name callable); otherwise the
    # unescaped output must not bypass the parent template's escaping.
    autoescape = environment.autoescape
    if callable(autoescape):
        autoescape = autoescape(cls.template)
    return Markup(rendered) if autoescape else rendered  # noqa: S704
