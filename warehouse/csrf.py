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

from pyramid.config.views import DefaultViewMapper
from pyramid.interfaces import IViewMapperFactory
from pyramid.httpexceptions import HTTPForbidden, HTTPMethodNotAllowed

from warehouse.utils.http import add_vary


REASON_NO_ORIGIN = "Origin checking failed - no Origin or Referer."
REASON_BAD_ORIGIN = "Origin checking failed - {} does not match {}."
REASON_BAD_TOKEN = "CSRF token missing or incorrect."


class InvalidCSRF(HTTPForbidden):
    pass


def csrf_exempt(view):
    @functools.wraps(view)
    def wrapped(context, request):
        request._process_csrf = False
        return view(context, request)
    return wrapped


def csrf_protect(view_or_scope):
    scope = None
    if isinstance(view_or_scope, str):
        scope = view_or_scope

    def inner(view):
        @functools.wraps(view)
        def wrapped(context, request):
            request._process_csrf = True
            request._csrf_scope = scope
            return view(context, request)
        return wrapped

    if scope is None:
        return inner(view_or_scope)
    else:
        return inner


def csrf_mapper_factory(mapper):
    class CSRFMapper(mapper):

        def __call__(self, view):
            view = super().__call__(view)

            # Check if the view has CSRF exempted, and if it is then we just
            # want to return the view without wrapping it.
            if not getattr(view, "_process_csrf", True):
                return view

            @functools.wraps(view)
            def wrapped(context, request):
                # Assign our view to an innerview function so that we can
                # modify it inside of the wrapped function.
                innerview = view

                # Check if we're processing CSRF for this request at all or
                # if it has been exempted from CSRF.
                if not getattr(request, "_process_csrf", True):
                    return innerview(context, request)

                # If we're processing CSRF for this request, then we want to
                # set a Vary: Cookie header on every response to ensure that
                # we don't cache the result of a CSRF check or a form with a
                # CSRF token in it.
                if getattr(request, "_process_csrf", None):
                    innerview = add_vary("Cookie")(innerview)

                # Assume that anything not defined as 'safe' by RFC2616 needs
                # protection
                if request.method not in {"GET", "HEAD", "OPTIONS", "TRACE"}:
                    # Determine if this request has set itself so that it
                    # should be protected against CSRF. If it has not and it's
                    # gotten one of these methods, then we want to raise an
                    # error stating that this resource does not support this
                    # method.
                    if not getattr(request, "_process_csrf", None):
                        raise HTTPMethodNotAllowed

                    if request.scheme == "https":
                        # Determine the origin of this request
                        origin = request.headers.get("Origin")
                        if origin is None:
                            origin = request.headers.get("Referer")

                        # Fail if we were not able to locate an origin at all
                        if not origin:
                            raise InvalidCSRF(REASON_NO_ORIGIN)

                        # Parse the origin and host for comparison
                        originp = urllib.parse.urlparse(origin)
                        hostp = urllib.parse.urlparse(request.host_url)

                        # Actually check our Origin against our Current
                        # Host URL.
                        if ((originp.scheme, originp.hostname, originp.port)
                                != (hostp.scheme, hostp.hostname, hostp.port)):
                            reason_origin = origin
                            if origin != "null":
                                reason_origin = urllib.parse.urlunparse(
                                    originp[:2] + ("", "", "", ""),
                                )

                            reason = REASON_BAD_ORIGIN.format(
                                reason_origin, request.host_url,
                            )

                            raise InvalidCSRF(reason)

                    session = getattr(request, "_session", request.session)

                    # Get the provided CSRF token from the request.
                    request_token = request.POST.get("csrf_token", "")
                    if not request_token:
                        request_token = request.headers.get("CSRFToken", "")

                    # Get our CSRF token from the session, scoped or not
                    # depending on if our @csrf_protect header was registered
                    # with a scope or not.
                    scope = request._csrf_scope
                    if scope is None:
                        csrf_token = session.get_csrf_token()
                    else:
                        csrf_token = session.get_scoped_csrf_token(scope)

                    if not hmac.compare_digest(csrf_token, request_token):
                        raise InvalidCSRF(REASON_BAD_TOKEN)

                return innerview(context, request)

            return wrapped
    return CSRFMapper


def includeme(config):
    # We need to commit what's happened so far so that we can get the current
    # default ViewMapper
    config.commit()

    # Get the current default ViewMapper, and create a subclass of it that
    # will wrap our view with CSRF checking.
    mapper = config.registry.queryUtility(IViewMapperFactory)
    if mapper is None:
        mapper = DefaultViewMapper
    config.set_view_mapper(csrf_mapper_factory(mapper))
