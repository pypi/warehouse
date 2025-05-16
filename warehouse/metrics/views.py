# SPDX-License-Identifier: Apache-2.0

from warehouse.metrics.interfaces import IMetricsService


def timing_view(view, info):
    def wrapper_view(context, request):
        metrics = request.find_service(IMetricsService, context=None)

        route_tag = "route:null"
        if request.matched_route:
            route_tag = f"route:{request.matched_route.name}"

        original_view = info.original_view
        if hasattr(original_view, "__qualname__"):
            view_name = f"{original_view.__module__}.{original_view.__qualname__}"
        elif hasattr(original_view, "__name__"):
            view_name = f"{original_view.__module__}.{original_view.__name__}"
        else:
            view_name = "unknown"
        view_tag = f"view:{view_name}"

        with metrics.timed("pyramid.view.duration", tags=[route_tag, view_tag]):
            return view(context, request)

    return wrapper_view
