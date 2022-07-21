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
from __future__ import annotations

import dataclasses
import inspect
import time
import types
import typing
import json

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable, ClassVar, Type, TypeVar

from pyramid.request import Request


T = TypeVar("T")
S = TypeVar("S")


class CaveatError(Exception):
    pass


class CaveatDeserializationError(CaveatError):
    pass


@dataclass(frozen=True, slots=True)
class Success:
    def __bool__(self):
        return True


@dataclass(frozen=True, slots=True)
class Failure:
    reason: str

    def __bool__(self):
        return False


Result = Success | Failure


@dataclass(frozen=True, slots=True, kw_only=True)
class Caveat:
    tag: ClassVar[int]

    def verify(self, request: Request, context: Any, permission: str) -> Result:
        raise NotImplementedError

    def __serialize__(self) -> Sequence:
        return (self.tag,) + dataclasses.astuple(self)

    @classmethod
    def __deserialize__(cls: Type[S], data: Any) -> S:
        if not isinstance(data, Sequence):
            raise CaveatDeserializationError(f"Must be a sequence, not a {type(data)}")

        valid = getattr(cls, "_valid_types", [])
        if len(data) > len(getattr(cls, "_valid_types")):
            raise CaveatDeserializationError(f"Too many values, expected {len(valid)}")

        kwargs = {}
        for i, field in enumerate(dataclasses.fields(cls)):
            if len(data) > i:
                value = data[i]
            elif field.default is not dataclasses.MISSING:
                value = field.default
            elif field.default_factory is not dataclasses.MISSING:
                value = field.default_factory()
            else:
                raise CaveatDeserializationError("Not enough values")

            if not isinstance(value, valid[i]):
                raise CaveatDeserializationError(
                    f"Invalid value: {value}, expected {valid[i]}"
                )

            kwargs[field.name] = value

        return cls(**kwargs)


class _CaveatRegistry:

    _tags: dict[int, Caveat]

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._tags = {}

    def add(self, tag: int, cls: Caveat):
        if tag in self._tags:
            raise TypeError(
                f"Cannot re-use tag: {tag}, already used by {self._tags[tag]}"
            )

        self._tags[tag] = cls
        cls.tag = tag

    def lookup(self, /, tag: int) -> Caveat:
        return self._tags.get(tag)


_caveat_registry = _CaveatRegistry()


def _resolve_types(t: Any) -> Any:
    if inspect.isclass(t):
        return t
    else:
        origin_type = typing.get_origin(t)
        if origin_type is typing.ClassVar:
            return _resolve_types(typing.get_args(t)[0])
        elif origin_type == types.UnionType:
            return tuple([_resolve_types(a) for a in typing.get_args(t)])
        raise TypeError(f"I can't resolve: {t}")


def as_caveat(*, tag: int) -> Callable[[Type[T]], Type[T]]:
    def deco(cls: Type[T]) -> Type[T]:
        cls._valid_types = [
            _resolve_types(t) for t in list(typing.get_type_hints(cls).values())[1:]
        ]
        _caveat_registry.add(tag, cls)
        return cls

    return deco


def serialize(caveat: Caveat) -> bytes:
    return json.dumps(
        caveat.__serialize__(), sort_keys=True, separators=(",", ":")
    ).encode("utf8")


def deserialize(data: bytes) -> Caveat:
    loaded = json.loads(data)

    if isinstance(loaded, Mapping):
        raise NotImplementedError  # Transform old to new

    if not isinstance(loaded, Sequence) or isinstance(loaded, str):
        raise CaveatDeserializationError("caveat must be an array")

    if not len(loaded):
        raise CaveatDeserializationError("caveat array cannot be empty")

    tag, *fields = loaded
    cls = _caveat_registry.lookup(tag)

    if cls is None:
        raise CaveatDeserializationError(f"caveat has unknown tag: {tag}")

    return cls.__deserialize__(fields)
