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

from pyramid.authentication import (
    BasicAuthAuthenticationPolicy as _BasicAuthAuthenticationPolicy,
    SessionAuthenticationPolicy as _SessionAuthenticationPolicy,
)

from warehouse.accounts.interfaces import IUserService
from warehouse.cache.http import add_vary_callback


class BasicAuthAuthenticationPolicy(_BasicAuthAuthenticationPolicy):

    def unauthenticated_userid(self, request):
        # If we're calling into this API on a request, then we want to register
        # a callback which will ensure that the response varies based on the
        # Authorization header.
        request.add_response_callback(add_vary_callback("Authorization"))

        # Dispatch to the real basic authentication policy
        username = super().unauthenticated_userid(request)

        # Assuming we got a username from the basic authentication policy, we
        # want to locate the userid from the IUserService.
        if username is not None:
            login_service = request.find_service(IUserService, context=None)
            return login_service.find_userid(username)


class SessionAuthenticationPolicy(_SessionAuthenticationPolicy):

    def unauthenticated_userid(self, request):
        # If we're calling into this API on a request, then we want to register
        # a callback which will ensure that the response varies based on the
        # Cookie header.
        request.add_response_callback(add_vary_callback("Cookie"))

        # Dispatch to the real SessionAuthenticationPolicy
        return super().unauthenticated_userid(request)
