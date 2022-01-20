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

import json

import redis

from warehouse import tasks
from warehouse.oidc.interfaces import IJWKService
from warehouse.utils import oidc


@tasks.task(bind=True, ignore_result=True, acks_late=True)
def update_oidc_jwks(self, request):
    with redis.StrictRedis.from_url(
        request.registry.settings.get("oidc.jwk_cache_url")
    ) as r:
        jwk_service = request.find_service(IJWKService)
        for (provider, keys) in jwk_service.fetch_keysets():
            r.set(oidc.jwk_cache_key(provider), json.dumps(keys))
