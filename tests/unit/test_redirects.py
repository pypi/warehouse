# SPDX-License-Identifier: Apache-2.0

import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPMovedPermanently

from warehouse import redirects


class TestRedirectView:
    def test_redirect_view(self, pyramid_request):
        target = "/{wat}/{_request.method}"
        view = redirects.redirect_view_factory(target)

        pyramid_request.matchdict = {"wat": "the-thing"}
        resp = view(pyramid_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/the-thing/GET"

    def test_redirect_view_raises_for_invalid_chars(self, pyramid_request):
        target = "/{wat}/{_request.method}"
        view = redirects.redirect_view_factory(target)
        pyramid_request.matchdict = {"wat": "the-thing\n"}

        with pytest.raises(
            HTTPBadRequest, match="URL may not contain control characters"
        ):
            view(pyramid_request)

    @pytest.mark.parametrize(
        "matched",
        [
            # Backslashes go into Location verbatim, but browsers treat
            # them as "/", which would steer /p/{name}/ redirects elsewhere
            # on the same origin (e.g. /account/logout/?next=...).
            "..\\account\\logout\\?next=",
            "name\\with\\backslash",
        ],
    )
    def test_redirect_view_raises_for_backslashes(self, matched, pyramid_request):
        target = "/project/{name}/"
        view = redirects.redirect_view_factory(target)
        pyramid_request.matchdict = {"name": matched}

        with pytest.raises(HTTPBadRequest):
            view(pyramid_request)


def test_add_redirect(pyramid_config, mocker):
    rview = mocker.sentinel.rview
    rview_factory = mocker.patch.object(
        redirects, "redirect_view_factory", autospec=True, return_value=rview
    )
    add_route = mocker.patch.object(pyramid_config, "add_route", autospec=True)
    add_view = mocker.patch.object(pyramid_config, "add_view", autospec=True)

    source = "/the/{thing}/"
    target = "/other/{thing}/"
    redirect = mocker.sentinel.redirect
    kwargs = {"redirect": redirect}

    redirects.add_redirect(pyramid_config, source, target, **kwargs)

    route_name = "warehouse.redirects." + source + str(kwargs)
    add_route.assert_called_once_with(route_name, source, **kwargs)
    add_view.assert_called_once_with(rview, route_name=route_name)
    rview_factory.assert_called_once_with(target, redirect=redirect)


def test_includeme(pyramid_config, mocker):
    add_directive = mocker.patch.object(pyramid_config, "add_directive", autospec=True)
    redirects.includeme(pyramid_config)
    add_directive.assert_called_once_with(
        "add_redirect", redirects.add_redirect, action_wrap=False
    )
