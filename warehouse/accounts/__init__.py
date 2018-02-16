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

from warehouse.accounts.interfaces import IUserService, ITokenService
from warehouse.accounts.services import (
    database_login_factory, TokenServiceFactory
)
from warehouse.accounts.auth_policy import (
    BasicAuthAuthenticationPolicy, SessionAuthenticationPolicy,
)
from warehouse.rate_limiting import RateLimit, IRateLimiter


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

    principals = []

    if user.is_superuser:
        principals.append("group:admins")

    return principals


def _user(request):
    userid = request.authenticated_userid

    if userid is None:
        return

    login_service = request.find_service(IUserService, context=None)
    return login_service.get_user(userid)


def includeme(config):
    # Register our login service
    config.register_service_factory(database_login_factory, IUserService)

    # Register our token services
    config.register_service_factory(
        TokenServiceFactory(name="password"),
        ITokenService,
        name="password",
    )
    config.register_service_factory(
        TokenServiceFactory(name="email"),
        ITokenService,
        name="email",
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

    # Register the rate limits that we're going to be using for our login
    # attempts
    config.register_service_factory(
        RateLimit("10 per 5 minutes"),
        IRateLimiter,
        name="user.login",
    )
    config.register_service_factory(
        RateLimit("1000 per 5 minutes"),
        IRateLimiter,
        name="global.login",
    )
