# SPDX-License-Identifier: Apache-2.0

"""Form values shaped like the ones WebOb parses out of a real request."""

import cgi

from webob.multidict import MultiDict


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
