# SPDX-License-Identifier: Apache-2.0

import pretend

from pyramid import events, viewderivers
from pyramid_retry import IBeforeRetry

from warehouse.metrics import (
    DataDogMetrics,
    IMetricsService,
    NullMetrics,
    _metrics,
    event_handlers,
    includeme,
    views,
)


def test_include_defaults_to_null():
    config = pretend.stub(
        registry=pretend.stub(settings={}),
        maybe_dotted=lambda i: i,
        register_service_factory=pretend.call_recorder(lambda factory, iface: None),
        add_request_method=pretend.call_recorder(lambda fn, name, reify: None),
        add_subscriber=pretend.call_recorder(lambda handler, event: None),
        add_view_deriver=pretend.call_recorder(lambda deriver, under: None),
    )
    includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(NullMetrics.create_service, IMetricsService)
    ]
    assert config.add_subscriber.calls == [
        pretend.call(event_handlers.on_new_request, events.NewRequest),
        pretend.call(event_handlers.on_before_traversal, events.BeforeTraversal),
        pretend.call(event_handlers.on_context_found, events.ContextFound),
        pretend.call(event_handlers.on_before_render, events.BeforeRender),
        pretend.call(event_handlers.on_new_response, events.NewResponse),
        pretend.call(event_handlers.on_before_retry, IBeforeRetry),
    ]
    assert config.add_view_deriver.calls == [
        pretend.call(views.timing_view, under=viewderivers.INGRESS)
    ]
    assert config.add_request_method.calls == [
        pretend.call(_metrics, name="metrics", reify=True)
    ]


def test_include_sets_class():
    config = pretend.stub(
        registry=pretend.stub(
            settings={"metrics.backend": "warehouse.metrics.DataDogMetrics"}
        ),
        maybe_dotted=lambda pth: {"warehouse.metrics.DataDogMetrics": DataDogMetrics}[
            pth
        ],
        register_service_factory=pretend.call_recorder(lambda factory, iface: None),
        add_request_method=pretend.call_recorder(lambda fn, name, reify: None),
        add_subscriber=pretend.call_recorder(lambda handler, event: None),
        add_view_deriver=pretend.call_recorder(lambda deriver, under: None),
    )
    includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(DataDogMetrics.create_service, IMetricsService)
    ]
    assert config.add_subscriber.calls == [
        pretend.call(event_handlers.on_new_request, events.NewRequest),
        pretend.call(event_handlers.on_before_traversal, events.BeforeTraversal),
        pretend.call(event_handlers.on_context_found, events.ContextFound),
        pretend.call(event_handlers.on_before_render, events.BeforeRender),
        pretend.call(event_handlers.on_new_response, events.NewResponse),
        pretend.call(event_handlers.on_before_retry, IBeforeRetry),
    ]
    assert config.add_view_deriver.calls == [
        pretend.call(views.timing_view, under=viewderivers.INGRESS)
    ]
    assert config.add_request_method.calls == [
        pretend.call(_metrics, name="metrics", reify=True)
    ]


def test_finds_service(pyramid_request):
    assert _metrics(pyramid_request) == pyramid_request.find_service(IMetricsService)
