# SPDX-License-Identifier: Apache-2.0
"""The Component base class."""

import dataclasses

from typing import Any, ClassVar

from pyramid_components.props import as_props_dataclass, props_to_context


@dataclasses.dataclass
class _EmptyProps:
    """Default props for components that declare none."""


class Component:
    """Base class for components.

    Subclasses set ``template`` (a path under a Jinja2 search root) and an inner
    ``Props`` class. ``Props`` is converted to a dataclass on subclass creation.
    """

    template: ClassVar[str]
    Props: ClassVar[type] = _EmptyProps

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Find the nearest user-defined Props in the MRO, skipping Component so
        # its _EmptyProps default never shadows a Props inherited from a mixin.
        for base in cls.__mro__:
            if base is Component:
                continue
            props = base.__dict__.get("Props")
            if props is not None:
                cls.Props = as_props_dataclass(props)
                break

    @classmethod
    def get_context(cls, props: Any) -> dict:
        """Return the template context. Override to derive or reshape data.

        A classmethod: components hold no instance state, so rendering never
        needs to construct one.
        """
        return props_to_context(props)
