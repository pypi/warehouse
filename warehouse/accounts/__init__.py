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

from pyramid.authentication import SessionAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy

from warehouse.accounts.interfaces import ILoginService
from warehouse.accounts.services import database_login_factory


def _authenticate(userid, request):
    login_service = request.find_service(ILoginService)
    user = login_service.get_user(userid)

    if user is None:
        return

    # Since we've already authenticated the user and fetched the user from the
    # database, we'll go ahead and stash the user. This will keep the user
    # inside of the SQLAlchemy identity map.
    request._user = user

    return []  # TODO: Add other principles.


def _user(request):
    userid = request.authenticated_userid

    if userid is None:
        return

    login_service = request.find_service(ILoginService)
    return login_service.get_user(userid)


def includeme(config):
    # Register our login service
    config.register_service_factory(database_login_factory, ILoginService)

    # Register our authentication and authorization policies
    config.set_authentication_policy(
        SessionAuthenticationPolicy(callback=_authenticate),
    )
    config.set_authorization_policy(ACLAuthorizationPolicy())

    # Add a request method which will allow people to access the user object.
    config.add_request_method(_user, name="user", reify=True)
