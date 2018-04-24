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
from pyramid.events import NewResponse

from warehouse.legacy.api.xmlrpc import on_new_response, includeme


def test_on_new_response_enabled():
    metric_name = pretend.stub()
    histogram = pretend.call_recorder(lambda metric_name, value: None)
    content_length = pretend.stub()
    new_response_event = pretend.stub(
        request=pretend.stub(
            content_length_metric_name=metric_name,
            registry=pretend.stub(datadog=pretend.stub(histogram=histogram)),
        ),
        response=pretend.stub(content_length=content_length)
    )

    on_new_response(new_response_event)

    assert histogram.calls == [
        pretend.call(metric_name, content_length),
    ]


def test_on_new_response_disabled():
    histogram = pretend.call_recorder(lambda metric_name, value: None)
    new_response_event = pretend.stub(
        request=pretend.stub(
            registry=pretend.stub(datadog=pretend.stub(histogram=histogram)),
        ),
    )

    on_new_response(new_response_event)

    assert histogram.calls == []


def test_includeme():
    config = pretend.stub(
        add_subscriber=pretend.call_recorder(lambda subscriber, iface: None),
    )

    includeme(config)

    assert config.add_subscriber.calls == [
        pretend.call(on_new_response, NewResponse),
    ]
