# SPDX-License-Identifier: Apache-2.0

import types

import pytest

from warehouse.metrics import views


class TestTimingView:
    @pytest.mark.parametrize("route", [None, "foo"])
    def test_unknown_view(self, mocker, pyramid_request, metrics, route):
        view = mocker.Mock(return_value=mocker.sentinel.response)
        view_info = types.SimpleNamespace(original_view=types.SimpleNamespace())

        derived = views.timing_view(view, view_info)

        pyramid_request.matched_route = (
            types.SimpleNamespace(name=route) if route else None
        )
        route_tag = "route:null" if route is None else f"route:{route}"

        assert derived(mocker.sentinel.context, pyramid_request) is (
            mocker.sentinel.response
        )
        view.assert_called_once_with(mocker.sentinel.context, pyramid_request)
        metrics.timed.assert_called_once_with(
            "pyramid.view.duration", tags=[route_tag, "view:unknown"]
        )

    @pytest.mark.parametrize("route", [None, "foo"])
    def test_qualname_view(self, mocker, pyramid_request, metrics, route):
        view = mocker.Mock(return_value=mocker.sentinel.response)
        view_info = types.SimpleNamespace(
            original_view=types.SimpleNamespace(
                __module__="foo", __qualname__="bar", __name__="other"
            )
        )

        derived = views.timing_view(view, view_info)

        pyramid_request.matched_route = (
            types.SimpleNamespace(name=route) if route else None
        )
        route_tag = "route:null" if route is None else f"route:{route}"

        assert derived(mocker.sentinel.context, pyramid_request) is (
            mocker.sentinel.response
        )
        view.assert_called_once_with(mocker.sentinel.context, pyramid_request)
        metrics.timed.assert_called_once_with(
            "pyramid.view.duration", tags=[route_tag, "view:foo.bar"]
        )

    @pytest.mark.parametrize("route", [None, "foo"])
    def test_name_view(self, mocker, pyramid_request, metrics, route):
        view = mocker.Mock(return_value=mocker.sentinel.response)
        view_info = types.SimpleNamespace(
            original_view=types.SimpleNamespace(__module__="foo", __name__="other")
        )

        derived = views.timing_view(view, view_info)

        pyramid_request.matched_route = (
            types.SimpleNamespace(name=route) if route else None
        )
        route_tag = "route:null" if route is None else f"route:{route}"

        assert derived(mocker.sentinel.context, pyramid_request) is (
            mocker.sentinel.response
        )
        view.assert_called_once_with(mocker.sentinel.context, pyramid_request)
        metrics.timed.assert_called_once_with(
            "pyramid.view.duration", tags=[route_tag, "view:foo.other"]
        )
