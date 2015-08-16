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

import urllib.parse

import requests

from zope.interface import implementer

from warehouse.cache.origin.interfaces import IOriginCache


@implementer(IOriginCache)
class FastlyCache:

    _api_domain = "https://api.fastly.com"

    def __init__(self, *, api_key, service_id):
        self.api_key = api_key
        self.service_id = service_id

    @classmethod
    def create_service(cls, context, request):
        return cls(
            api_key=request.registry.settings["origin_cache.api_key"],
            service_id=request.registry.settings["origin_cache.service_id"],
        )

    def _mkurl(self, key):
        path = "/service/{service_id}/purge/{key}".format(
            service_id=self.service_id,
            key=key,
        )
        return urllib.parse.urljoin(self._api_domain, path)

    def cache(self, keys, request, response, *, seconds=None):
        response.headers["Surrogate-Key"] = " ".join(keys)

        if seconds is not None:
            response.headers["Surrogate-Control"] = \
                "max-age={}".format(seconds)

    def purge(self, keys):
        with requests.session() as session:
            for key in keys:
                resp = session.post(
                    self._mkurl(key),
                    headers={
                        "Accept": "application/json",
                        "Fastly-Key": self.api_key,
                        "Fastly-Soft-Purge": "1",
                    },
                )
                resp.raise_for_status()
