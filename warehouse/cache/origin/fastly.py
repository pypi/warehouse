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

from zope.interface import implementer

from warehouse.cache.origin.interfaces import IOriginCache


@implementer(IOriginCache)
class FastlyCache:

    def cache(self, keys, request, response):
        response.headers["Surrogate-Key"] = " ".join(keys)

    def purge(self, keys):
        raise NotImplementedError  # TODO: Implement Purging


def includeme(config):
    # Ensure that pyramid_services has been registered.
    config.include("pyramid_services")

    # Register an IOriginCache which will handle interfacing with Fastly.
    config.register_service(FastlyCache(), IOriginCache)
