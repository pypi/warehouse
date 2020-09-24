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

from warehouse.tuf.interfaces import IKeyService, IRepositoryService, IStorageService
from warehouse.tuf.tasks import add_target
from warehouse.tuf.utils import GCSBackend, LocalBackend, make_fileinfo


class InsecureKeyWarning(UserWarning):
    pass


@implementer(IKeyService)
class LocalKeyService:
    def __init__(self, key_path, request):
        warnings.warn(
            "LocalKeyService is intended only for use in development, you "
            "should not use it in production to avoid unnecessary key exposure.",
            InsecureKeyWarning,
        )

        self._key_path = key_path
        self._request = request

    @classmethod
    def create_service(cls, context, request):
        return cls(request.registry.settings["tuf.key.path"], request)

    def pubkeys_for_role(self, rolename):
        pubkey_path = os.path.join(self._key_path, f"tuf.{rolename}.pub")
        return [repository_tool.import_ed25519_publickey_from_file(pubkey_path)]

    def privkeys_for_role(self, rolename):
        privkey_path = os.path.join(self._key_path, f"tuf.{rolename}")
        return [
            repository_tool.import_ed25519_privatekey_from_file(
                privkey_path,
                password=self._request.registry.settings[f"tuf.{rolename}.secret"],
            )
        ]


@implementer(IStorageService)
class LocalStorageService:
    def __init__(self, request):
        self._store = LocalBackend(request)

    @classmethod
    def create_service(cls, context, request):
        return cls(request)

    def get_backend(self):
        return self._store


@implementer(IStorageService)
class GCSStorageService:
    def __init__(self, request):
        self._store = GCSBackend(request)

    @classmethod
    def create_service(cls, context, request):
        return cls(request)

    def get_backend(self):
        return self._store


@implementer(IRepositoryService)
class LocalRepositoryService:
    def __init__(self, repo_path, executor):
        self._repo_path = repo_path
        self._executor = executor

    @classmethod
    def create_service(cls, context, request):
        return cls(
            request.registry.settings["tuf.repo.path"],
            request.task(add_target).delay,
        )

    def load_repository(self):
        return repository_tool.load_repository(self._repo_path)

    def add_target(self, file, custom=None):
        fileinfo = make_fileinfo(file, custom=custom)
        self._executor(file.path, fileinfo)


@implementer(IRepositoryService)
class GCSRepositoryService:
    def __init__(self, executor, request):
        self._store = GCSBackend(request)

    @classmethod
    def create_service(cls, context, request):
        return cls(request.task(add_target).delay, request)

    def load_repository(self):
        return repository_tool.load_repository("tuf", storage_backend=self._store)

    def add_target(self, file, custom=None):
        fileinfo = make_fileinfo(file, custom=custom)
        self._executor(file.path, fileinfo)
