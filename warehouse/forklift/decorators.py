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
            raise _exc_with_message(
                HTTPForbidden,
                "Read-only mode: Uploads are temporarily disabled.",
            )

        # After that, we want to check if we're disallowing new uploads, which is
        # functionally the same as read only mode, but only for the upload endpoint.
        if request.flags.enabled(AdminFlagValue.DISALLOW_NEW_UPLOAD):
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
            raise _exc_with_message(
                HTTPForbidden,
                "Invalid or non-existent authentication information. "
                "See {projecthelp} for more information.".format(
                    projecthelp=request.help_url(_anchor="invalid-auth")
                ),
            )

        # These checks only make sense when our authenticated identity is a user,
        # not a project identity (like OIDC-minted tokens.)
        if request.user:
            # Ensure that user has a verified, primary email address. This should both
            # reduce the ease of spam account creation and activity, as well as act as
            # a forcing function for https://github.com/pypa/warehouse/issues/3632.
            # TODO: Once https://github.com/pypa/warehouse/issues/3632 has been solved,
            #       we might consider a different condition, possibly looking at
            #       User.is_active instead.
            if not (request.user.primary_email and request.user.primary_email.verified):
                raise _exc_with_message(
                    HTTPForbidden,
                    (
                        "User {!r} does not have a verified primary email address. "
                        "Please add a verified primary email before attempting to "
                        "upload to PyPI. See {project_help} for more information."
                    ).format(
                        request.user.username,
                        project_help=request.help_url(_anchor="verified-email"),
                    ),
                )

        # Otherwise, we'll just dispatch to our underlying view
        return wrapped(context, request)

    return wrapper
