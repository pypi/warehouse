# Copyright 2014 Donald Stufft
#
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
import hmac
import urllib.parse

from flask import session
from werkzeug.exceptions import SecurityError

from warehouse.utils import random_token, vary_by


def _verify_csrf_origin(request):
    # Determine the origin of this request
    origin = request.headers.get("Origin", request.headers.get("Referer"))

    # Fail if we were not able to locate an origin at all
    if origin is None:
        raise SecurityError("Origin checking failed - no Origin or Referer.")

    # Parse the origin and host for comparison
    origin_parsed = urllib.parse.urlparse(origin)
    host_parsed = urllib.parse.urlparse(request.host_url)

    # Fail if our origin is null
    if origin == "null":
        raise SecurityError(
            "Origin checking failed - null does not match {}.".format(
                urllib.parse.urlunparse(host_parsed[:2] + ("", "", "", ""))
            )
        )

    # Fail if the received origin does not match the host
    if ((origin_parsed.scheme, origin_parsed.hostname, origin_parsed.port) !=
            (host_parsed.scheme, host_parsed.hostname, host_parsed.port)):
        raise SecurityError(
            "Origin checking failed - {} does not match {}.".format(
                urllib.parse.urlunparse(origin_parsed[:2] + ("", "", "", "")),
                urllib.parse.urlunparse(host_parsed[:2] + ("", "", "", "")),
            )
        )


def _verify_csrf_token(request):
    # Get the token out of the session
    csrf_token = session.get("user.csrf")

    # Validate that we have a stored token, if we do not then we have nothing
    # to compare the incoming token against.
    if csrf_token is None:
        raise SecurityError("CSRF token not set.")

    # Attempt to look in the form data
    request_token = request.form.get("csrf_token")

    # Also attempt to look in the headers, this makes things like Ajax easier
    # and PUT/DELETE possible.
    request_token = request.headers.get("X-CSRF-Token", request_token)

    # Validate that we have a token attached to this request somehow
    if not request_token:
        raise SecurityError("CSRF token missing.")

    # Validate that the stored token and the request token match each other
    if not hmac.compare_digest(csrf_token, request_token):
        raise SecurityError("CSRF token incorrect.")


def _ensure_csrf_token(request):
    # Store a token in the session if one doesn't exist there already
    #   Note: We have to use the private request._session because
    #         request.session is not guaranteed to exist when this function is
    #         called.
    if not session.get("user.csrf"):
        session["user.csrf"] = random_token()

    # Store the fact that CSRF is in use for this request on the request
    request._csrf = True


def handle_csrf(
    request, view,
    _verify_origin=_verify_csrf_origin,
    _verify_token=_verify_csrf_token
):

    # Assume that anything not defined as 'safe' by RFC2616 needs
    # protection
    if request.method not in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        # We have 3 potential states for a view function to be in, it could
        # have asked for CSRF, exempted for CSRF, or done none of these.

        if getattr(view, "_csrf", None) is None:
            # CSRF influences the response and thus we cannot know if it is
            # safe to access the session or if that will inadvertently
            # trigger the response to require a Vary: Cookie so if the
            # function has not explicitly told us one way or another we
            # will always hard fail on an unsafe method.
            raise SecurityError("No CSRF protection applied to view")

        elif getattr(view, "_csrf", None):
            # The function has explicitly opted in to the CSRF protection
            # and we ca assume that it has handled setting up the CSRF
            # token as well as making sure that a Vary: Cookie header has
            # been added.
            _verify_origin(request)
            _verify_token(request)

    # Ensure that the session has a token stored for this request. This is
    # purposely done *after* we've validated the CSRF above. If there is
    # no CSRF token stored we want that to be a distinct messages from if
    # the given token doesn't match a new, random, token.
    if getattr(view, "_csrf", None):
        _ensure_csrf_token(request)


def csrf_protect(fn):
    # Mark the view function as requiring CSRF
    fn._csrf = True

    # Return the original view function, but varied by Cookie
    return vary_by("Cookie")(fn)


def csrf_exempt(fn):
    # Mark the view function as exempt from CSRF
    fn._csrf = False

    # Return the original view function
    return fn


def csrf_cycle(session):
    # Store a token in the session if one doesn't exist there already
    #   Note: We have to use the session inside of the environ dictionary
    #         because request.session does not exist when this function runs
    session["user.csrf"] = random_token()
