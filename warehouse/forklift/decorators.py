# SPDX-License-Identifier: Apache-2.0

import cgi

from pyramid.httpexceptions import HTTPBadRequest, HTTPForbidden

from warehouse.admin.flags import AdminFlagValue
from warehouse.forklift.utils import _exc_with_message


def sanitize(wrapped):
    """
    Wraps a Pyramid view to sanitize the incoming request of "bad" values.

    There's a lot of garbage that gets sent to the upload view, which we'll
    sanitize to clean that up and/or fail early rather than getting failures
    deeper in the stack.
    """

    def wrapper(context, request):
        # Do some cleanup of the various form fields, there's a lot of garbage that
        # gets sent to this view, and this helps prevent issues later on.
        for key in list(request.POST):
            value = request.POST.get(key)
            if isinstance(value, str):
                # distutils "helpfully" substitutes unknown, but "required" values
                # with the string "UNKNOWN". This is basically never what anyone
                # actually wants so we'll just go ahead and delete anything whose
                # value is UNKNOWN.
                if value.strip() == "UNKNOWN":
                    del request.POST[key]

                # Escape NUL characters, which psycopg doesn't like
                if "\x00" in value:
                    request.POST[key] = value.replace("\x00", "\\x00")

        # Check if any fields were supplied as a tuple and have become a
        # FieldStorage. The 'content' field _should_ be a FieldStorage, however,
        # and we don't care about the legacy gpg_signature field.
        # ref: https://github.com/pypi/warehouse/issues/2185
        # ref: https://github.com/pypi/warehouse/issues/2491
        for field in set(request.POST) - {"content", "gpg_signature"}:
            values = request.POST.getall(field)
            if any(isinstance(value, cgi.FieldStorage) for value in values):
                request.metrics.increment(
                    "warehouse.upload.failed",
                    tags=["reason:field-is-tuple", f"field:{field}"],
                )
                raise _exc_with_message(
                    HTTPBadRequest, f"{field}: Should not be a tuple."
                )

        # Otherwise, we'll just dispatch to our underlying view
        return wrapped(context, request)

    return wrapper


def ensure_uploads_allowed(wrapped):
    """
    Ensures that we're currently allowing uploads, either generally or for the
    current request.identity.
    """

    def wrapper(context, request):
        # The very first thing we want to check, is whether we're currently in
        # read only mode, because if we're in read only mode nothing else matters.
        if request.flags.enabled(AdminFlagValue.READ_ONLY):
            request.metrics.increment(
                "warehouse.upload.failed", tags=["reason:read-only"]
            )
            raise _exc_with_message(
                HTTPForbidden, "Read-only mode: Uploads are temporarily disabled."
            )

        # After that, we want to check if we're disallowing new uploads, which is
        # functionally the same as read only mode, but only for the upload endpoint.
        if request.flags.enabled(AdminFlagValue.DISALLOW_NEW_UPLOAD):
            request.metrics.increment(
                "warehouse.upload.failed", tags=["reason:uploads-disabled"]
            )
            raise _exc_with_message(
                HTTPForbidden,
                "New uploads are temporarily disabled. "
                "See {projecthelp} for more information.".format(
                    projecthelp=request.help_url(_anchor="admin-intervention")
                ),
            )

        # Before we do anything else, if there isn't an authenticated identity with
        # this request, then we'll go ahead and bomb out.
        if request.identity is None:
            request.metrics.increment(
                "warehouse.upload.failed", tags=["reason:no-identity"]
            )
            raise _exc_with_message(
                HTTPForbidden,
                "Invalid or non-existent authentication information. "
                "See {projecthelp} for more information.".format(
                    projecthelp=request.help_url(_anchor="invalid-auth")
                ),
            )

        # Otherwise, we'll just dispatch to our underlying view
        return wrapped(context, request)

    return wrapper
