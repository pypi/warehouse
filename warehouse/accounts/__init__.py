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

import datetime

from pyramid.authorization import ACLAuthorizationPolicy
from pyramid_multiauth import MultiAuthenticationPolicy

from warehouse.accounts.interfaces import (
    IPasswordRecoveryService, IUserService
)
from warehouse.accounts.services import (
    database_login_factory, PasswordRecoveryService
)
from warehouse.accounts.auth_policy import (
    BasicAuthAuthenticationPolicy, SessionAuthenticationPolicy,
)

REDIRECT_FIELD_NAME = 'next'


def _login(username, password, request):
    login_service = request.find_service(IUserService, context=None)
    userid = login_service.find_userid(username)
    if userid is not None:
        if login_service.check_password(userid, password):
            login_service.update_user(
                userid,
                last_login=datetime.datetime.utcnow(),
            )
            return _authenticate(userid, request)


def _authenticate(userid, request):
    login_service = request.find_service(IUserService, context=None)
    user = login_service.get_user(userid)

    if user is None:
        return

    return []  # TODO: Add other principles.


def _user(request):
    userid = request.authenticated_userid

    if userid is None:
        return

    login_service = request.find_service(IUserService, context=None)
    return login_service.get_user(userid)


def includeme(config):
    # Register our login service
    config.register_service_factory(database_login_factory, IUserService)

    # Register password recovery service
    config.register_service(
        PasswordRecoveryService(
            config.registry.settings["password_recovery.url"],
            config.registry.settings["password_recovery.secret"]
        ),
        IPasswordRecoveryService,
    )

    # Register our authentication and authorization policies
    config.set_authentication_policy(
        MultiAuthenticationPolicy([
            SessionAuthenticationPolicy(callback=_authenticate),
            BasicAuthAuthenticationPolicy(check=_login),
        ]),
    )
    config.set_authorization_policy(ACLAuthorizationPolicy())

    # Add a request method which will allow people to access the user object.
    config.add_request_method(_user, name="user", reify=True)
