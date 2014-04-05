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
import functools
import hmac
import urllib.parse

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
    #   Note: We have to use the private request._session because
    #         request.session is not guaranteed to exist when this function is
    #         called.
    csrf_token = request._session.get("user.csrf")

    # Validate that we have a stored token, if we do not then we have nothing
    # to compare the incoming token against.
    if csrf_token is None:
        raise SecurityError("CSRF token not set.")

    request_token = None

    # Attempt to look in the form data if this request was a POST request
    if request.method == "POST":
        request_token = request.form.get("csrf_token", request_token)

    # Also attempt to look in the headers, this makes things like Ajax easier
    # and PUT/DELETE possible.
    request_token = request.headers.get("X-CSRFToken", request_token)

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
    if not request._session.get("user.csrf"):
        request._session["user.csrf"] = random_token()

    # Store the fact that CSRF is in use for this request on the request
    request._csrf = True


def handle_csrf(fn):
    """
    CSRF mitigation which adds two layers of protection against CSRF attacks,
    the implementation of which assumes that for reasonable compatability with
    the web at large that this site is hosted with TLS and the
    Strict-Transport-Security header.


    Strict Origin Based
    -------------------

    Strictly verify that the Origin or Referer headers of any particular
    "unsafe" request matches the expected origin for this service. In
    particular this check will:

    1. First, determine the origin of the request by attempting to use the
       Origin header if it exists, or falling back to the Referer header if it
       doesn't.
    2. Secondly, determine the expected origin for this service first by
       attempting to use the Host header, and falling back to SERVER_NAME:PORT
       otherwise.
    3. Finally verify that we have all of the required information, and that
       the origin of the request matches the expected origin for this service
       or fail otherwise.


    Secret Token Based
    ------------------

    Strictly verify that the request included a secure token that is only known
    to the application. This token will be stored inside of the session and
    should be included as part of any form or ajax request that the application
    makes.
    """

    @functools.wraps(fn)
    def wrapped(self, view, app, request, *args, **kwargs):
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
                _verify_csrf_origin(request)
                _verify_csrf_token(request)

        # Ensure that the session has a token stored for this request. This is
        # purposely done *after* we've validated the CSRF above. If there is
        # no CSRF token stored we want that to be a distinct messages from if
        # the given token doesn't match a new, random, token.
        if getattr(view, "_csrf", None):
            _ensure_csrf_token(request)

        # If we've gotten to this point, than either the request was a "safe"
        # method, the view has opted out of CSRF, or the CSRF has been
        # verified. In any case it *should* be safe to actually process this
        # request.
        return fn(self, view, app, request, *args, **kwargs)

    return wrapped


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
