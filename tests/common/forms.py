# SPDX-License-Identifier: Apache-2.0

"""Form values shaped like the ones WebOb parses out of a real request."""

import cgi
import io

import pytest

from webob.compat import cgi_FieldStorage
from webob.multidict import MultiDict


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
