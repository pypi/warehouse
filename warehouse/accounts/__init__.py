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

from pyramid.authorization import ACLAuthorizationPolicy

from warehouse.accounts.interfaces import (
    IPasswordBreachedService,
    ITokenService,
    IUserService,
)
from warehouse.accounts.security_policy import (
    BasicAuthSecurityPolicy,
    SessionSecurityPolicy,
    TwoFactorAuthorizationPolicy,
)
from warehouse.accounts.services import (
    HaveIBeenPwnedPasswordBreachedService,
    NullPasswordBreachedService,
    TokenServiceFactory,
    database_login_factory,
)
from warehouse.macaroons.security_policy import (
    MacaroonAuthorizationPolicy,
    MacaroonSecurityPolicy,
)
from warehouse.rate_limiting import IRateLimiter, RateLimit
from warehouse.utils.security_policy import MultiSecurityPolicy

__all__ = ["NullPasswordBreachedService", "HaveIBeenPwnedPasswordBreachedService"]


REDIRECT_FIELD_NAME = "next"


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
        TokenServiceFactory(name="password"), ITokenService, name="password"
    )
    config.register_service_factory(
        TokenServiceFactory(name="email"), ITokenService, name="email"
    )
    config.register_service_factory(
        TokenServiceFactory(name="two_factor"), ITokenService, name="two_factor"
    )

    # Register our password breach detection service.
    breached_pw_class = config.maybe_dotted(
        config.registry.settings.get(
            "breached_passwords.backend", HaveIBeenPwnedPasswordBreachedService
        )
    )
    config.register_service_factory(
        breached_pw_class.create_service, IPasswordBreachedService
    )

    # Register our security policies (AuthN + AuthZ)
    authz_policy = TwoFactorAuthorizationPolicy(
        policy=MacaroonAuthorizationPolicy(policy=ACLAuthorizationPolicy())
    )
    config.set_security_policy(
        MultiSecurityPolicy(
            [
                SessionSecurityPolicy(),
                BasicAuthSecurityPolicy(),
                MacaroonSecurityPolicy(),
            ],
            authz_policy,
        )
    )

    # Add a request method which will allow people to access the user object.
    config.add_request_method(_user, name="user", reify=True)

    # Register the rate limits that we're going to be using for our login
    # attempts and account creation
    user_login_ratelimit_string = config.registry.settings.get(
        "warehouse.account.user_login_ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(user_login_ratelimit_string), IRateLimiter, name="user.login"
    )
    ip_login_ratelimit_string = config.registry.settings.get(
        "warehouse.account.ip_login_ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(ip_login_ratelimit_string), IRateLimiter, name="ip.login"
    )
    global_login_ratelimit_string = config.registry.settings.get(
        "warehouse.account.global_login_ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(global_login_ratelimit_string), IRateLimiter, name="global.login"
    )
    email_add_ratelimit_string = config.registry.settings.get(
        "warehouse.account.email_add_ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(email_add_ratelimit_string), IRateLimiter, name="email.add"
    )
    password_reset_ratelimit_string = config.registry.settings.get(
        "warehouse.account.password_reset_ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(password_reset_ratelimit_string), IRateLimiter, name="password.reset"
    )
