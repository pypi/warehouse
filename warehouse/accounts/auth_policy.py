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
)

from warehouse.accounts.interfaces import ILoginService


class BasicAuthAuthenticationPolicy(_BasicAuthAuthenticationPolicy):

    def unauthenticated_userid(self, request):
        username = super().unauthenticated_userid(request)

        if username is not None:
            login_service = request.find_service(ILoginService, context=None)
            return login_service.find_userid(username)
