# SPDX-License-Identifier: Apache-2.0

import datetime


def now() -> datetime.datetime:
    """Return the current datetime in UTC without a timezone."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def dotted_navigator(path):
    def method(self):
        obj = self
        for item in path.split("."):
            obj = getattr(obj, item)
        return obj

    return property(method)
