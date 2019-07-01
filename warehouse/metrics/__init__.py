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

from pyramid import events, viewderivers
from pyramid_retry import IBeforeRetry

from warehouse.metrics import event_handlers
from warehouse.metrics.interfaces import IMetricsService
from warehouse.metrics.services import DataDogMetrics, NullMetrics
from warehouse.metrics.views import timing_view

__all__ = ["IMetricsService", "NullMetrics", "DataDogMetrics", "includeme"]


def includeme(config):
    # Register our metrics service.
    metrics_class = config.maybe_dotted(
        config.registry.settings.get("metrics.backend", NullMetrics)
    )
    config.register_service_factory(metrics_class.create_service, IMetricsService)

    # Register our timing events.
    config.add_subscriber(event_handlers.on_new_request, events.NewRequest)
    config.add_subscriber(event_handlers.on_before_traversal, events.BeforeTraversal)
    config.add_subscriber(event_handlers.on_context_found, events.ContextFound)
    config.add_subscriber(event_handlers.on_before_render, events.BeforeRender)
    config.add_subscriber(event_handlers.on_new_response, events.NewResponse)
    config.add_subscriber(event_handlers.on_before_retry, IBeforeRetry)

    # Register our view deriver that ensures we get our view timed.
    config.add_view_deriver(timing_view, under=viewderivers.INGRESS)
