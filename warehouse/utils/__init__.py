# SPDX-License-Identifier: Apache-2.0

import datetime


def now(tz=False) -> datetime.datetime:
    """Return the current datetime in UTC with or without a timezone."""
    now = datetime.datetime.now(datetime.UTC)
    return now if tz else now.replace(tzinfo=None)


def dotted_navigator(path):
    def method(self):
        obj = self
        for item in path.split("."):
            obj = getattr(obj, item)
        return obj

    return property(method)
