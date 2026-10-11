# SPDX-License-Identifier: Apache-2.0

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

_SUBSCRIBERS = [
    (event_handlers.on_new_request, events.NewRequest),
    (event_handlers.on_before_traversal, events.BeforeTraversal),
    (event_handlers.on_context_found, events.ContextFound),
    (event_handlers.on_before_render, events.BeforeRender),
    (event_handlers.on_new_response, events.NewResponse),
    (event_handlers.on_before_retry, IBeforeRetry),
]


def _config(mocker, settings, maybe_dotted):
    config = mocker.Mock(
        spec=[
            "registry",
            "maybe_dotted",
            "register_service_factory",
            "add_request_method",
            "add_subscriber",
            "add_view_deriver",
        ]
    )
    config.registry.settings = settings
    config.maybe_dotted.side_effect = maybe_dotted
    return config


def test_include_defaults_to_null(mocker):
    config = _config(mocker, settings={}, maybe_dotted=lambda i: i)

    includeme(config)

    config.register_service_factory.assert_called_once_with(
        NullMetrics.create_service, IMetricsService
    )
    assert config.add_subscriber.call_args_list == [
        mocker.call(handler, event) for handler, event in _SUBSCRIBERS
    ]
    config.add_view_deriver.assert_called_once_with(
        views.timing_view, under=viewderivers.INGRESS
    )
    config.add_request_method.assert_called_once_with(
        _metrics, name="metrics", reify=True
    )


def test_include_sets_class(mocker):
    config = _config(
        mocker,
        settings={"metrics.backend": "warehouse.metrics.DataDogMetrics"},
        maybe_dotted=lambda pth: {"warehouse.metrics.DataDogMetrics": DataDogMetrics}[
            pth
        ],
    )

    includeme(config)

    config.register_service_factory.assert_called_once_with(
        DataDogMetrics.create_service, IMetricsService
    )
    assert config.add_subscriber.call_args_list == [
        mocker.call(handler, event) for handler, event in _SUBSCRIBERS
    ]
    config.add_view_deriver.assert_called_once_with(
        views.timing_view, under=viewderivers.INGRESS
    )
    config.add_request_method.assert_called_once_with(
        _metrics, name="metrics", reify=True
    )


def test_finds_service(pyramid_request):
    assert _metrics(pyramid_request) == pyramid_request.find_service(IMetricsService)
