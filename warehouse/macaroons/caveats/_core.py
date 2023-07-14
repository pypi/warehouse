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
import json
import typing

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, TypeVar

from pydantic import ValidationError
from pydantic.dataclasses import dataclass as pydantic_dataclass
from pyramid.request import Request

from warehouse.macaroons.caveats import _legacy

T = TypeVar("T")


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


@pydantic_dataclass(frozen=True)
class Caveat:
    tag: ClassVar[int]

    def verify(self, request: Request, context: Any, permission: str) -> Result:
        raise NotImplementedError

    def __serialize__(self) -> Sequence:
        return (self.tag,) + dataclasses.astuple(self)

    @classmethod
    def __deserialize__(cls: type[Caveat], data: Sequence) -> Caveat:
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

            kwargs[field.name] = value

        try:
            obj = cls(**kwargs)
        except ValidationError:
            raise CaveatDeserializationError("invalid values for fields")

        return obj


class _CaveatRegistry:
    _tags: dict[int, type[Caveat]]

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._tags = {}

    def add(self, tag: int, cls: type[Caveat]):
        if tag in self._tags:
            raise TypeError(
                f"Cannot re-use tag: {tag}, already used by {self._tags[tag]}"
            )

        self._tags[tag] = cls
        cls.tag = tag

    def lookup(self, /, tag: int) -> type[Caveat] | None:
        return self._tags.get(tag)


_caveat_registry = _CaveatRegistry()


# TODO: The return signature detected is `"Union[Type[Dataclass], DataclassProxy]"`,
# but the expectation is `Type[Dataclass]`.
# See https://github.com/pydantic/pydantic/issues/4498 but not exactly the same.
# This might not be corrected in pydantic until 2.0.
# Original signature with type hints:
# def as_caveat(*, tag: int) -> Callable[[type[T]], type[T]]:
def as_caveat(*, tag: int):
    def deco(cls: type[T]) -> type[T]:
        _caveat_registry.add(tag, typing.cast(type[Caveat], cls))
        return cls

    return deco


def serialize(caveat: Caveat) -> bytes:
    return json.dumps(
        caveat.__serialize__(), sort_keys=True, separators=(",", ":")
    ).encode("utf8")


def deserialize(data: bytes) -> Caveat:
    loaded = json.loads(data)

    # Our original caveats were implemented as a mapping with arbitrary keys,
    # so if we've gotten one of our those, we'll attempt to adapt it to our
    # new format.
    if isinstance(loaded, Mapping):
        loaded = _legacy.adapt(loaded)
        if loaded is None:
            raise CaveatDeserializationError("caveat must be an array")

    if not isinstance(loaded, Sequence) or isinstance(loaded, str):
        raise CaveatDeserializationError("caveat must be an array")

    if not len(loaded):
        raise CaveatDeserializationError("caveat array cannot be empty")

    tag, *fields = loaded
    cls = _caveat_registry.lookup(tag)

    if cls is None:
        raise CaveatDeserializationError(f"caveat has unknown tag: {tag}")

    return cls.__deserialize__(fields)
