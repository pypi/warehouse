# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from warehouse.metrics import views


class TestTimingView:
    @pytest.mark.parametrize("route", [None, "foo"])
    def test_unknown_view(self, pyramid_services, metrics, route):
        response = pretend.stub()
        view = pretend.call_recorder(lambda request, context: response)
        view_info = pretend.stub(original_view=pretend.stub())

        derived = views.timing_view(view, view_info)

        request = pretend.stub(
            matched_route=pretend.stub(name=route) if route else None,
            find_service=pyramid_services.find_service,
        )
        context = pretend.stub()

        route_tag = "route:null" if route is None else f"route:{route}"

        assert derived(context, request) is response
        assert view.calls == [pretend.call(context, request)]
        assert metrics.timed.calls == [
            pretend.call("pyramid.view.duration", tags=[route_tag, "view:unknown"])
        ]

    @pytest.mark.parametrize("route", [None, "foo"])
    def test_qualname_view(self, pyramid_services, metrics, route):
        response = pretend.stub()
        view = pretend.call_recorder(lambda request, context: response)
        view_info = pretend.stub(
            original_view=pretend.stub(
                __module__="foo", __qualname__="bar", __name__="other"
            )
        )

        derived = views.timing_view(view, view_info)

        request = pretend.stub(
            matched_route=pretend.stub(name=route) if route else None,
            find_service=pyramid_services.find_service,
        )
        context = pretend.stub()

        route_tag = "route:null" if route is None else f"route:{route}"

        assert derived(context, request) is response
        assert view.calls == [pretend.call(context, request)]
        assert metrics.timed.calls == [
            pretend.call("pyramid.view.duration", tags=[route_tag, "view:foo.bar"])
        ]

    @pytest.mark.parametrize("route", [None, "foo"])
    def test_name_view(self, pyramid_services, metrics, route):
        response = pretend.stub()
        view = pretend.call_recorder(lambda request, context: response)
        view_info = pretend.stub(
            original_view=pretend.stub(__module__="foo", __name__="other")
        )

        derived = views.timing_view(view, view_info)

        request = pretend.stub(
            matched_route=pretend.stub(name=route) if route else None,
            find_service=pyramid_services.find_service,
        )
        context = pretend.stub()

        route_tag = "route:null" if route is None else f"route:{route}"

        assert derived(context, request) is response
        assert view.calls == [pretend.call(context, request)]
        assert metrics.timed.calls == [
            pretend.call("pyramid.view.duration", tags=[route_tag, "view:foo.other"])
        ]
