# SPDX-License-Identifier: Apache-2.0

from warehouse.i18n import LazyString


def object_encode(obj):
    if isinstance(obj, LazyString):
        # NOTE: This expands the lazy string based on the locale in the current request.
        # This is almost certainly what we want, but could conceivably cause
        # issues for users who issue a request, change their locale, and then
        # receive an email at some later date in their original locale.
        return str(obj)
    return obj
