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

from pyramid.events import NewResponse

import warehouse.legacy.api.xmlrpc.views  # noqa


def on_new_response(new_response_event):
    request = new_response_event.request
    if not hasattr(request, 'content_length_metric_name'):
        return

    request.registry.datadog.histogram(
        request.content_length_metric_name,
        new_response_event.response.content_length
    )


def includeme(config):
    config.add_subscriber(on_new_response, NewResponse)
