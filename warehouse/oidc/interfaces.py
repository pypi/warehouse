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


class IJWKService(Interface):
    def create_service(context, request):
        """
        Create the service, given the context and request for which it is
        being created.
        """
        pass

    def get_key(provider, key_id):
        """
        Return the JWK identified by the given KID for the given provider,
        fetching it if not already cached locally.

        Returns None if the JWK does not exist or the access pattern is
        invalid (i.e., exceeds our internal limit on JWK requests to
        each provider).
        """
        pass
