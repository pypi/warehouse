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


from pyramid.events import (
    ApplicationCreated,
    NewResponse,
    NewRequest,
    ContextFound,
    BeforeTraversal,
    BeforeRender)


def time_ms():
    return time.time() * 1000


def configure_metrics(config, datadog_metrics):
    '''
    * datadog_metrics: datadog metrics object initialized by user
    '''
    config.registry.datadog = datadog_metrics


def on_app_created(app_created_event):
    registry = app_created_event.app.registry
    datadog = registry.datadog
    datadog.event(
        'Pyramid application started',
        'Pyramid application started'
    )


def on_new_request(new_request_event):
    request = new_request_event.request
    request.timings = {'new_request_start': time_ms()}


def on_before_traversal(before_traversal_event):
    request = before_traversal_event.request

    timings = request.timings
    timings['route_match_duration'] = time_ms() - timings['new_request_start']

    request.registry.datadog.timing(
        'pyramid.request.duration.route_match',
        timings['route_match_duration'],
    )


def on_context_found(context_found_event):
    request = context_found_event.request

    timings = request.timings
    timings['traversal_duration'] = time_ms() - timings['new_request_start']
    timings['view_code_start'] = time_ms()

    request.registry.datadog.timing(
        'pyramid.request.duration.traversal',
        timings['traversal_duration'],
    )


def on_before_render(before_render_event):
    request = before_render_event['request']

    timings = request.timings
    if "view_code_start" in timings:
        timings['view_duration'] = time_ms() - timings['view_code_start']
    timings['before_render_start'] = time_ms()

    route_tag = 'route:null'
    if request.matched_route:
        route_tag = 'route:%s' % request.matched_route.name

    if "view_duration" in timings:
        request.registry.datadog.timing(
            'pyramid.request.duration.view',
            timings['view_duration'],
            tags=[route_tag],
        )


def on_new_response(new_response_event):
    request = new_response_event.request
    if not hasattr(request, 'timings'):
        return
    new_response_time = time_ms()

    timings = request.timings
    timings['request_duration'] = \
        new_response_time - timings['new_request_start']

    tags = []
    datadog = request.registry.datadog

    if request.matched_route:
        route_tag = 'route:%s' % request.matched_route.name
        tags.append(route_tag)

        if 'before_render_start' in timings:
            timings['template_render_duration'] = \
                new_response_time - timings['before_render_start']

            datadog.timing(
                'pyramid.request.duration.template_render',
                timings['template_render_duration'],
                tags=tags,
            )

    status_code = str(new_response_event.response.status_code)
    datadog.timing(
        'pyramid.request.duration.total',
        timings['request_duration'],
        tags=tags + [
            'status_code:%s' % status_code,
            'status_type:%sxx' % status_code[0]
        ],
    )


def includeme(config):
    '''
    Events are triggered in the following chronological order:
    NewRequest > BeforeTraversal > ContextFound > BeforeRender > NewResponse
    Note that not all events may be triggered depending on the request scenario
    eg. 404 Not Found would not trigger ContextFound event.
    '''
    config.add_directive('configure_metrics', configure_metrics)
    config.add_subscriber(on_app_created, ApplicationCreated)
    config.add_subscriber(on_new_request, NewRequest)
    config.add_subscriber(on_before_traversal, BeforeTraversal)
    config.add_subscriber(on_context_found, ContextFound)
    config.add_subscriber(on_before_render, BeforeRender)
    config.add_subscriber(on_new_response, NewResponse)
