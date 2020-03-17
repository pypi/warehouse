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

    def get_pubkeys():
        """
        Return a list of (TUF-formatted) public keys for the TUF role that this
        service was initialized with.
        """

    def get_privkeys():
        """
        Return a list of (TUF-formatted) private keys for the TUF role that this
        service was initialized with.
        """


class IRepositoryService(Interface):
    def create_service(context, request):
        """
        Create the service, given the context and request for which it is being
        created.
        """

    def add_target(file, backsigned=False):
        """
        Given a warehouse.packaging.models.File, add it to the TUF
        repository.
        """
