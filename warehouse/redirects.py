# SPDX-License-Identifier: Apache-2.0

import re

from pyramid.httpexceptions import HTTPBadRequest, HTTPMovedPermanently

# WSGI servers reject header values containing control characters. Gunicorn
# validates against ``[ \t\x21-\x7e\x80-\xff]``, so anything in the C0 range
# (plus DEL) makes it raise InvalidHeader from start_response. That escapes as
# an unhandled exception and is answered by gunicorn's own error page, which
# echoes the offending value back, rather than by the 400 we intend here.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def redirect_view_factory(target, redirect=HTTPMovedPermanently, **kw):
    def redirect_view(request):
        redirect_to = target.format(_request=request, **request.matchdict)

        # Check to see if any of the characters that we can't represent in a
        # header exist in our target, if so we'll raise a BadRequest
        if _CONTROL_CHARS.search(redirect_to):
            raise HTTPBadRequest("URL may not contain control characters")

        # Backslashes go into the Location header verbatim, but browsers
        # treat them as "/" in http(s) URLs (WHATWG). A redirect target of
        # "/project/..\account\logout\..." would walk straight to
        # "/account/logout/", so refuse them.
        if "\\" in redirect_to:
            raise HTTPBadRequest("URL may not contain backslashes")

        return redirect(redirect_to)

    return redirect_view


def add_redirect(config, source, target, **kw):
    route_name = "warehouse.redirects." + source + str(kw)

    config.add_route(route_name, source, **kw)
    config.add_view(redirect_view_factory(target, **kw), route_name=route_name)


def includeme(config):
    config.add_directive("add_redirect", add_redirect, action_wrap=False)
