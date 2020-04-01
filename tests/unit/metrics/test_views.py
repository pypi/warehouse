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
