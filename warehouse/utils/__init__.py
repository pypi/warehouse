# SPDX-License-Identifier: Apache-2.0

import datetime as dt


def now(tz=False) -> dt.datetime:
    """Return the current datetime in UTC with or without a timezone."""
    now = dt.datetime.now(dt.UTC)
    return now if tz else now.replace(tzinfo=None)


def dotted_navigator(path):
    def method(self):
        obj = self
        for item in path.split("."):
            obj = getattr(obj, item)
        return obj

    return property(method)
