# SPDX-License-Identifier: Apache-2.0

"""Form values shaped like the ones WebOb parses out of a real request."""

import cgi
import io

from collections.abc import Iterable, Mapping

import pyramid.testing
import pytest

from webob.compat import cgi_FieldStorage
from webob.multidict import MultiDict, NestedMultiDict, NoVars


def file_part(
    file: io.BytesIO | None = None,
    filename: str = "upload.bin",
    type: str = "application/octet-stream",
) -> cgi.FieldStorage:
    """
    Build a parsed multipart file part, as WebOb posts for a chosen file.

    ``webob.compat.cgi_FieldStorage`` is the class WebOb hands a view; its
    ``__repr__`` does not read the body the way ``cgi``'s does. An empty file
    input posts ``b""`` instead. A real part has a ``list`` of None, so
    ``bool()`` on it raises. The explicit environ keeps the constructor from
    parsing ``sys.argv``.
    """
    part: cgi.FieldStorage = cgi_FieldStorage(  # type: ignore[call-arg]
        environ={"QUERY_STRING": ""}
    )
    part.filename = filename
    part.type = type
    part.file = io.BytesIO() if file is None else file
    part.list = None
    return part


UNUSABLE_IDS = ["nope", "", pytest.param(file_part(), id="file-part")]
"""Posted ids that can never match a row: not a UUID, empty, or a file."""


def as_posted(data: dict) -> MultiDict:
    """
    Encode scalar WTForms data (str, numbers, dates, bools, files) as posted.

    An unchecked box or a None field posts nothing, a file posts its part, and
    every other value posts as its string form. Lists, enums and datetimes
    need encoding by hand.
    """
    posted: MultiDict = MultiDict()
    for key, value in data.items():
        if value is None or value is False:
            continue
        posted[key] = value if isinstance(value, cgi.FieldStorage) else str(value)
    return posted


class FormItems(list[tuple[str, str | bytes | cgi.FieldStorage]]):
    """
    MultiDict storage that refuses any value WebOb would never parse.

    WebOb posts str, a FieldStorage for a chosen file, or bytes for a part
    with an empty filename (``b""`` for an empty file input).
    A test that sets any other value (such as a UUID object) hands a view a
    value it can never receive.
    """

    def __init__(self, items: Iterable[tuple[str, object]] = ()) -> None:
        super().__init__()
        self.extend(items)

    def append(self, item: tuple[str, object]) -> None:
        key, value = item
        if not isinstance(value, str | bytes | cgi.FieldStorage):
            raise TypeError(
                f"form value for {key!r} is {type(value).__name__}; "
                "a form only posts str, bytes or FieldStorage"
            )
        super().append((key, value))

    def extend(self, items: Iterable[tuple[str, object]]) -> None:
        for item in items:
            self.append(item)


def as_form(values: MultiDict | Mapping[str, object]) -> MultiDict:
    """
    Guard a MultiDict so every later write goes through FormItems.

    A MultiDict is guarded in place, so a test that keeps a reference and
    writes to it after assigning still reaches the request. A plain mapping is
    copied. ``NoVars`` passes through, and a ``NestedMultiDict`` has each of
    its dicts guarded the same way.
    """
    if isinstance(values, NoVars | NestedMultiDict):
        if isinstance(values, NestedMultiDict):
            values.dicts = tuple(as_form(d) for d in values.dicts)
        return values
    if not isinstance(values, MultiDict):
        values = MultiDict(values)
    if not isinstance(values._items, FormItems):  # type: ignore[attr-defined]
        values._items = FormItems(values._items)  # type: ignore[attr-defined]
    return values


class FormAttribute:
    """A request attribute that guards whatever is assigned with ``as_form``."""

    def __set_name__(self, owner: type, name: str) -> None:
        self.storage = f"_{name}"

    def __get__(self, request: object, owner: type | None = None) -> MultiDict:
        return getattr(request, self.storage)

    def __set__(
        self, request: object, values: MultiDict | Mapping[str, object]
    ) -> None:
        setattr(request, self.storage, as_form(values))


class FormRequest(pyramid.testing.DummyRequest):
    """A DummyRequest whose GET, POST and params only hold form values."""

    GET = FormAttribute()
    POST = FormAttribute()
    params = FormAttribute()

    def __init__(
        self, params: MultiDict | Mapping[str, object] | None = None, **kwargs
    ) -> None:
        super().__init__(params=as_form({} if params is None else params), **kwargs)
        # DummyRequest stores extra keyword arguments in __dict__, which the
        # descriptors shadow, so route GET= and POST= through them.
        for name in ("GET", "POST"):
            if name in kwargs:
                setattr(self, name, kwargs[name])
