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

import warehouse.legacy.api.xmlrpc.views  # noqa

from warehouse.rate_limiting import IRateLimiter, RateLimit


def includeme(config):
    ratelimit_string = config.registry.settings.get(
        "warehouse.xmlrpc.client.ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(ratelimit_string), IRateLimiter, name="xmlrpc.client"
    )
