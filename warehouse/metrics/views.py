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
