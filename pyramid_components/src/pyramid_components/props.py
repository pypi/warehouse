# SPDX-License-Identifier: Apache-2.0
"""Binding of a component's inner ``Props`` class to a dataclass.

A component author writes ``class Props(pc.Props)`` with annotations and defaults; the
framework turns it into a dataclass so that ``Props(**kwargs)`` validates required and
unknown keys. Annotations are not runtime-type-checked in v1.
"""

import dataclasses

from typing import Any, dataclass_transform


@dataclass_transform(field_specifiers=(dataclasses.field,))
class Props:
    """Base for a component's inner ``Props``.

    Carries no runtime behavior. Inheriting it is what lets a type checker see the
    dataclass conversion below, so ``Props(**kwargs)`` call sites get checked
    instead of being read as a zero-argument constructor.
    """


def as_props_dataclass(props_cls: type) -> type:
    """Return ``props_cls`` as a dataclass. Idempotent for existing dataclasses.

    Checks ``__dataclass_fields__`` in the class' own ``__dict__`` because
    ``dataclasses.is_dataclass`` is satisfied by inheritance: a ``Props``
    subclassing another component's would come back undecorated, dropping every
    field it declares.
    """
    if "__dataclass_fields__" in props_cls.__dict__:
        return props_cls
    return dataclasses.dataclass(props_cls)


def props_to_context(props: Any) -> dict:
    """Return the default template context for a bound props instance.

    A shallow per-field mapping, not ``dataclasses.asdict``: values must reach the
    template as-is (asdict would deep-copy every value and flatten dataclass-valued
    props into plain dicts, breaking attribute access in templates).
    """
    return {f.name: getattr(props, f.name) for f in dataclasses.fields(props)}
