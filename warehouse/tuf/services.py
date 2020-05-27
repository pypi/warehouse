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


import os.path
import warnings

from tuf import repository_tool
from zope.interface import implementer

from warehouse.tuf.interfaces import IKeyService, IRepositoryService
from warehouse.tuf.tasks import add_target


class InsecureKeyWarning(UserWarning):
    pass


@implementer(IKeyService)
class LocalKeyService:
    def __init__(self, key_path, role, key_secret):
        warnings.warn(
            "LocalKeyService is intended only for use in development, you "
            "should not use it in production to avoid unnecessary key exposure.",
            InsecureKeyWarning,
        )

        self._key_path = key_path
        self._role = role
        self._key_secret = key_secret

    @classmethod
    def create_service(cls, context, request):
        return cls(
            request.registry.settings["tuf.key.path"],
            context,
            request.registry.settings[f"tuf.{context}.secret"],
        )

    def get_pubkeys(self):
        pubkey_path = os.path.join(self._key_path, f"tuf.{self._role}.pub")
        return [repository_tool.import_ed25519_publickey_from_file(pubkey_path)]

    def get_privkeys(self):
        privkey_path = os.path.join(self._key_path, f"tuf.{self._role}")
        return [
            repository_tool.import_ed25519_privatekey_from_file(
                privkey_path, password=self._key_secret
            )
        ]


@implementer(IRepositoryService)
class LocalRepositoryService:
    def __init__(self, executor):
        self.executor = executor

    @classmethod
    def create_service(cls, context, request):
        return cls(request.task(add_target).delay)

    def add_target(self, file, custom=None):
        self.executor(file, custom=custom)
