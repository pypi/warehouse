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

import hvac

from zope.interface import implementer

from warehouse.tuf.interfaces import IKeyService


@implementer(IKeyService)
class VaultKeyService:
    def __init__(self, request):
        self._vault = hvac.Client(
            url=request.registry.settings["vault.url"],
            token=request.registry.settings["vault.token"]
            # TODO: cert, verify
        )
        self._request = request

    @classmethod
    def create_service(cls, _context, request):
        return cls(request)

    def keys_for_role(self, rolename):
        raise NotImplementedError
