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

# Adapted from code originally licensed as:

# The MIT License (MIT)
#
# Copyright (c) 2016 SurveyMonkey
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import time

from warehouse.metrics.interfaces import IMetricsService


def time_ms():
    return time.time() * 1000


def on_new_request(new_request_event):
    request = new_request_event.request
    request.timings = {"new_request_start": time_ms()}


def on_before_traversal(before_traversal_event):
    request = before_traversal_event.request

    timings = request.timings
    timings["route_match_duration"] = time_ms() - timings["new_request_start"]

    metrics = request.find_service(IMetricsService, context=None)
    metrics.timing(
        "pyramid.request.duration.route_match", timings["route_match_duration"]
    )


def on_context_found(context_found_event):
    request = context_found_event.request

    timings = request.timings
    timings["traversal_duration"] = time_ms() - timings["new_request_start"]
    timings["view_code_start"] = time_ms()

    metrics = request.find_service(IMetricsService, context=None)
    metrics.timing("pyramid.request.duration.traversal", timings["traversal_duration"])


def on_before_render(before_render_event):
    request = before_render_event["request"]

    timings = request.timings
    if "view_code_start" in timings:
        timings["view_duration"] = time_ms() - timings["view_code_start"]
    timings["before_render_start"] = time_ms()

    route_tag = "route:null"
    if request.matched_route:
        route_tag = "route:%s" % request.matched_route.name

    if "view_duration" in timings:
        metrics = request.find_service(IMetricsService, context=None)
        metrics.timing(
            "pyramid.request.duration.view", timings["view_duration"], tags=[route_tag]
        )


def on_new_response(new_response_event):
    request = new_response_event.request
    if not hasattr(request, "timings"):
        return
    new_response_time = time_ms()

    timings = request.timings
    timings["request_duration"] = new_response_time - timings["new_request_start"]

    tags = []
    metrics = request.find_service(IMetricsService, context=None)

    if request.matched_route:
        route_tag = "route:%s" % request.matched_route.name
        tags.append(route_tag)

        if "before_render_start" in timings:
            timings["template_render_duration"] = (
                new_response_time - timings["before_render_start"]
            )

            metrics.timing(
                "pyramid.request.duration.template_render",
                timings["template_render_duration"],
                tags=tags,
            )

    status_code = str(new_response_event.response.status_code)
    metrics.timing(
        "pyramid.request.duration.total",
        timings["request_duration"],
        tags=tags
        + ["status_code:%s" % status_code, "status_type:%sxx" % status_code[0]],
    )


def on_before_retry(event):
    request = event.request
    metrics = request.find_service(IMetricsService, context=None)

    route_tag = "route:null"
    if request.matched_route:
        route_tag = "route:%s" % request.matched_route.name

    metrics.increment("pyramid.request.retry", tags=[route_tag])
