# SPDX-License-Identifier: Apache-2.0

from pyramid.httpexceptions import HTTPBadRequest, HTTPMovedPermanently


def redirect_view_factory(target, redirect=HTTPMovedPermanently, **kw):
    def redirect_view(request):
        redirect_to = target.format(_request=request, **request.matchdict)

        # Check to see if any of the characters that we can't represent in a
        # header exist in our target, if so we'll raise a BadRequest
        if set(redirect_to) & {"\n", "\r"}:
            raise HTTPBadRequest("URL may not contain control characters")

        return redirect(redirect_to)

    return redirect_view


def add_redirect(config, source, target, **kw):
    route_name = "warehouse.redirects." + source + str(kw)

    config.add_route(route_name, source, **kw)
    config.add_view(redirect_view_factory(target, **kw), route_name=route_name)


def includeme(config):
    config.add_directive("add_redirect", add_redirect, action_wrap=False)
