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

import datetime

import freezegun
import pretend
import pytest

from warehouse.metrics.event_handlers import (
    on_before_render,
    on_before_retry,
    on_before_traversal,
    on_context_found,
    on_new_request,
    on_new_response,
    time_ms,
)


def test_time_ms():
    now = datetime.datetime.now(datetime.UTC)
    with freezegun.freeze_time(now):
        assert time_ms() == now.timestamp() * 1000


def test_on_new_request(pyramid_request):
    assert not hasattr(pyramid_request, "timings")

    now = datetime.datetime.now(datetime.UTC)
    with freezegun.freeze_time(now):
        on_new_request(pretend.stub(request=pyramid_request))

    assert pyramid_request.timings == {"new_request_start": now.timestamp() * 1000}


def test_on_before_traversal(pyramid_request, metrics):
    new_request = datetime.datetime.now(datetime.UTC)
    route_match_duration = new_request + datetime.timedelta(seconds=1)

    pyramid_request.timings = {"new_request_start": new_request.timestamp() * 1000}

    with freezegun.freeze_time(route_match_duration):
        on_before_traversal(pretend.stub(request=pyramid_request))

    assert metrics.timing.calls == [
        pretend.call("pyramid.request.duration.route_match", 1000)
    ]
    assert pyramid_request.timings == {
        "new_request_start": new_request.timestamp() * 1000,
        "route_match_duration": (
            route_match_duration.timestamp() - new_request.timestamp()
        )
        * 1000,
    }


def test_on_context_found(pyramid_request, metrics):
    new_request = datetime.datetime.now(datetime.UTC)
    traversal_duration = new_request + datetime.timedelta(seconds=2)
    view_code_start = new_request + datetime.timedelta(seconds=2)

    pyramid_request.timings = {"new_request_start": new_request.timestamp() * 1000}

    with freezegun.freeze_time(traversal_duration):
        on_context_found(pretend.stub(request=pyramid_request))

    assert metrics.timing.calls == [
        pretend.call("pyramid.request.duration.traversal", 2000)
    ]
    assert pyramid_request.timings == {
        "new_request_start": new_request.timestamp() * 1000,
        "traversal_duration": (traversal_duration.timestamp() - new_request.timestamp())
        * 1000,
        "view_code_start": view_code_start.timestamp() * 1000,
    }


class TestOnBeforeRender:
    def test_without_view_duration(self, pyramid_request, metrics):
        before_render_start = datetime.datetime.now(datetime.UTC)

        pyramid_request.timings = {}
        pyramid_request.matched_route = None

        with freezegun.freeze_time(before_render_start):
            on_before_render({"request": pyramid_request})

        assert metrics.timing.calls == []
        assert pyramid_request.timings == {
            "before_render_start": before_render_start.timestamp() * 1000
        }

    @pytest.mark.parametrize(
        ("matched_route", "route_tag"),
        [(None, "route:null"), (pretend.stub(name="foo"), "route:foo")],
    )
    def test_with_view_duration(
        self, pyramid_request, metrics, matched_route, route_tag
    ):
        view_code_start = datetime.datetime.now(datetime.UTC)
        before_render_start = view_code_start + datetime.timedelta(seconds=1.5)

        pyramid_request.timings = {
            "view_code_start": view_code_start.timestamp() * 1000
        }
        pyramid_request.matched_route = matched_route

        with freezegun.freeze_time(before_render_start):
            on_before_render({"request": pyramid_request})

        assert metrics.timing.calls == [
            pretend.call("pyramid.request.duration.view", 1500, tags=[route_tag])
        ]
        assert pyramid_request.timings == {
            "view_code_start": view_code_start.timestamp() * 1000,
            "view_duration": 1500.0,
            "before_render_start": before_render_start.timestamp() * 1000,
        }


class TestOnNewResponse:
    def test_without_timings(self, pyramid_request, metrics):
        on_new_response(pretend.stub(request=pyramid_request))

        assert metrics.timing.calls == []

    def test_without_route(self, pyramid_request, metrics):
        response = pretend.stub(status_code="200")

        new_request = datetime.datetime.now(datetime.UTC)
        new_response = new_request + datetime.timedelta(seconds=1)

        pyramid_request.timings = {"new_request_start": new_request.timestamp() * 1000}
        pyramid_request.matched_route = None

        with freezegun.freeze_time(new_response):
            on_new_response(pretend.stub(request=pyramid_request, response=response))

        assert metrics.timing.calls == [
            pretend.call(
                "pyramid.request.duration.total",
                1000,
                tags=["status_code:200", "status_type:2xx"],
            )
        ]
        assert pyramid_request.timings == {
            "new_request_start": new_request.timestamp() * 1000,
            "request_duration": 1000.0,
        }

    def test_without_render(self, pyramid_request, metrics):
        response = pretend.stub(status_code="200")

        new_request = datetime.datetime.now(datetime.UTC)
        new_response = new_request + datetime.timedelta(seconds=1)

        pyramid_request.timings = {"new_request_start": new_request.timestamp() * 1000}
        pyramid_request.matched_route = pretend.stub(name="thing")

        with freezegun.freeze_time(new_response):
            on_new_response(pretend.stub(request=pyramid_request, response=response))

        assert metrics.timing.calls == [
            pretend.call(
                "pyramid.request.duration.total",
                1000,
                tags=["route:thing", "status_code:200", "status_type:2xx"],
            )
        ]
        assert pyramid_request.timings == {
            "new_request_start": new_request.timestamp() * 1000,
            "request_duration": 1000.0,
        }

    def test_with_render(self, pyramid_request, metrics):
        response = pretend.stub(status_code="200")

        new_request = datetime.datetime.now(datetime.UTC)
        before_render = new_request + datetime.timedelta(seconds=1)
        new_response = new_request + datetime.timedelta(seconds=2)

        pyramid_request.timings = {
            "new_request_start": new_request.timestamp() * 1000,
            "before_render_start": before_render.timestamp() * 1000,
        }
        pyramid_request.matched_route = pretend.stub(name="thing")

        with freezegun.freeze_time(new_response):
            on_new_response(pretend.stub(request=pyramid_request, response=response))

        assert metrics.timing.calls == [
            pretend.call(
                "pyramid.request.duration.template_render", 1000, tags=["route:thing"]
            ),
            pretend.call(
                "pyramid.request.duration.total",
                2000,
                tags=["route:thing", "status_code:200", "status_type:2xx"],
            ),
        ]
        assert pyramid_request.timings == {
            "new_request_start": new_request.timestamp() * 1000,
            "before_render_start": before_render.timestamp() * 1000,
            "template_render_duration": 1000.0,
            "request_duration": 2000.0,
        }


class TestOnBeforeRetry:
    @pytest.mark.parametrize(
        ("matched_route", "route_tag"),
        [(None, "route:null"), (pretend.stub(name="foo"), "route:foo")],
    )
    def test_emits_metric(self, pyramid_request, metrics, matched_route, route_tag):
        pyramid_request.matched_route = matched_route

        on_before_retry(pretend.stub(request=pyramid_request))

        assert metrics.increment.calls == [
            pretend.call("pyramid.request.retry", tags=[route_tag])
        ]
