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

from zope.interface import Interface


class IKeyService(Interface):
    def create_service(context, request):
        """
        Create the service, given the context and request for which it is being
        created.
        """

    def get(rolename):
        """Return a key from specific rolename"""


class IStorageService(Interface):
    def create_service(context, request):
        """
        Create the service, given the context and request for which it is being
        created.
        """

    def get(rolename, version):
        """
        Return metadata from specific role name, optionally specific version.
        """

    def put(file_object, filename):
        """
        Stores file object with a specific filename.

        An alias to store() to be compatible with
        ``tuf.api.metadata.StorageBackendInterface``
        """

    def store(file_object, filename):
        """
        Stores file object with a specific filename.
        """


class IRepositoryService(Interface):
    def create_service(context, request):
        """
        Create the service, given the context and request for which it is being
        created.
        """

    def init_dev_repository():
        """
        Initializes a Metadata Repository from scratch, including a new root.
        """

    def init_targets_delegation():
        """
        Delegate targets role bins further delegates to the bin-n roles,
        which sign for all distribution files belonging to registered PyPI
        projects.
        """

    def bump_snapshot():
        """
        Bump the Snapshot Metadata Role
        """

    def bump_bin_n_roles():
        """
        Bump all BIN-N delegate roles Metadata
        """

    def add_hashed_targets(targets):
        """
        Add hashed Targets

        Args:
            targets: list of dictionary with file ``info`` and ``path``.

                ``info`` contains a dict with ``lenght``, ``hashes`` optionally
                ``custom`` nested dictionary.
                ``path`` file path

                Example:
                ```
                [
                    {
                        "info": {
                            "hashes": {"blake2b-256": file.blake2_256_digest},
                            "lenght": 256,
                            "custom": {"key": "value},
                        },
                        "path": "/xx/yy/file.tar.gz"
                    }
                ]
        """
