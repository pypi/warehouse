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

from pyramid import events
from pyramid_retry import IBeforeRetry

from warehouse.metrics import (
    includeme,
    NullMetrics,
    DataDogMetrics,
    IMetricsService,
    event_handlers,
)


def test_include_defaults_to_null():
    config = pretend.stub(
        registry=pretend.stub(settings={}),
        maybe_dotted=lambda i: i,
        register_service_factory=pretend.call_recorder(lambda factory, iface: None),
        add_subscriber=pretend.call_recorder(lambda handler, event: None),
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


def test_include_sets_class():
    config = pretend.stub(
        registry=pretend.stub(
            settings={"metrics.backend": "warehouse.metrics.DataDogMetrics"}
        ),
        maybe_dotted=lambda pth: {"warehouse.metrics.DataDogMetrics": DataDogMetrics}[
            pth
        ],
        register_service_factory=pretend.call_recorder(lambda factory, iface: None),
        add_subscriber=pretend.call_recorder(lambda handler, event: None),
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
