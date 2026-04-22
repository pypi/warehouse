# SPDX-License-Identifier: Apache-2.0

import cgi

from pyramid.httpexceptions import HTTPForbidden

from warehouse.admin.flags import AdminFlagValue
from warehouse.forklift.errors import ForkliftError


class InvalidTupleField(
    ForkliftError,
    message="{field}: Should not be a tuple.",
    tags={"reason:field-is-tuple", "field:{field}"},
):
    pass


class NoFileUpload(
    ForkliftError,
    message="Upload payload does not have a file.",
    tags={"reason:no-file"},
):
    pass


class InvalidContentType(
    ForkliftError,
    message="Invalid distribution file.",
    tags={"reason:invalid-content-type"},
):
    pass


class ReadOnlyEnabled(
    ForkliftError,
    error_type=HTTPForbidden,
    message="Read-only mode: Uploads are temporarily disabled.",
    tags={"reason:read-only"},
):
    pass


class UploadsDisabled(
    ForkliftError,
    error_type=HTTPForbidden,
    message="New uploads are temporarily disabled.",
    help_anchor="admin-intervention",
    tags={"reason:uploads-disabled"},
):
    pass


class MissingIdentity(
    ForkliftError,
    error_type=HTTPForbidden,
    message="Invalid or non-existent authentication information.",
    help_anchor="invalid-auth",
    tags={"reason:no-identity"},
):
    pass


class UnverifiedEmail(
    ForkliftError,
    error_type=HTTPForbidden,
    message=(
        "User {username!r} does not have a verified primary email address. "
        "Please add a verified primary email before attempting to "
        "upload to PyPI."
    ),
    help_anchor="verified-email",
    tags={"reason:unverified-email"},
):
    pass


class MissingTwoFactor(
    ForkliftError,
    error_type=HTTPForbidden,
    message=(
        "User {username!r} does not have two-factor authentication enabled. "
        "Please enable two-factor authentication before attempting to "
        "upload to PyPI."
    ),
    help_anchor="two-factor-authentication",
    tags={"reason:no-2fa"},
):
    pass


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
                raise InvalidTupleField(field=field)

        # Ensure that we have file data in the request.
        if "content" not in request.POST:
            raise NoFileUpload

        # Check the content type of what is being uploaded
        if not request.POST["content"].type or request.POST["content"].type.startswith(
            "image/"
        ):
            raise InvalidContentType

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
            raise ReadOnlyEnabled

        # After that, we want to check if we're disallowing new uploads, which is
        # functionally the same as read only mode, but only for the upload endpoint.
        if request.flags.enabled(AdminFlagValue.DISALLOW_NEW_UPLOAD):
            raise UploadsDisabled

        # Before we do anything else, if there isn't an authenticated identity with
        # this request, then we'll go ahead and bomb out.
        if request.identity is None:
            raise MissingIdentity

        # Otherwise, we'll just dispatch to our underlying view
        return wrapped(context, request)

    return wrapper
