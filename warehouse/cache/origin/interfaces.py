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


class IOriginCache(Interface):

    def create_service(context, request):
        """
        Create the service, given the context and request for which it is being
        created for.
        """

    def cache(keys, request, response, *, seconds=None):
        """
        A hook that will be called after the request has been processed, used
        to associate the request and/or the response with the origin cache
        keys.

        The seconds argument is optional, and if provided should be used to
        override the number of seconds the origin cache will store the object.
        """

    def purge(keys):
        """
        Purge and responses associated with the specific keys.
        """
