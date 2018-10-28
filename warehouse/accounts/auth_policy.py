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

from pymacaroons import Verifier
from pymacaroons.caveat_delegates import ThirdPartyCaveatVerifierDelegate
from pymacaroons.exceptions import MacaroonException

from pyramid.authentication import (
    BasicAuthAuthenticationPolicy as _BasicAuthAuthenticationPolicy,
    CallbackAuthenticationPolicy as _CallbackAuthenticationPolicy,
    SessionAuthenticationPolicy as _SessionAuthenticationPolicy,
)

from pyramid.interfaces import IAuthenticationPolicy, IAuthorizationPolicy
from pyramid.security import Denied
from pyramid.threadlocal import get_current_request

from zope.interface import implementer

from warehouse.accounts.interfaces import IAccountTokenService, IUserService
from warehouse.cache.http import add_vary_callback


class PassThroughThirdPartyCaveats(ThirdPartyCaveatVerifierDelegate):
    def verify_third_party_caveat(self, *args, **kwargs):
        return True


@implementer(IAuthenticationPolicy)
class AccountTokenAuthenticationPolicy(_CallbackAuthenticationPolicy):
    def __init__(self, authenticate, routes_allowed):
        self._authenticate = authenticate
        self.callback = self._auth_callback

        self._routes_allowed = routes_allowed

    def unauthenticated_userid(self, request):
        if request.matched_route.name not in self._routes_allowed:
            return None

        # If we're calling into this API on a request, then we want to register
        # a callback which will ensure that the response varies based on the
        # Authorization header.
        request.add_response_callback(add_vary_callback("Authorization"))

        account_token_service = request.find_service(IAccountTokenService, context=None)

        (
            unverified_macaroon,
            account_token,
        ) = account_token_service.get_unverified_macaroon()

        if account_token is None:
            return None

        # Validate authentication properties of the macaroon
        try:
            verifier = Verifier()
            verifier.third_party_caveat_verifier_delegate = (
                PassThroughThirdPartyCaveats()
            )

            verifier.satisfy_general(self._validate_first_party_caveat_authentication)

            verifier.verify(unverified_macaroon, account_token.secret)

        except MacaroonException:
            return None

        # Macaroon verified, so update last used and return user
        account_token_service.update_last_used(account_token.id)
        login_service = request.find_service(IUserService, context=None)
        return login_service.find_userid(account_token.username)

    def remember(self, request, userid, **kw):
        """A no-op. Let other authenticators handle this."""
        return []

    def forget(self, request):
        """A no-op. Let other authenticators handle this."""
        return []

    def _validate_first_party_caveat_authentication(self, caveat):
        """Validate caveats relating to authentication."""
        # TODO: Decide on caveat language and implement authentication caveats
        # here (things like not_before, not_after).
        return True

    def _auth_callback(self, userid, request):
        return self._authenticate(userid, request)


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
            return str(login_service.find_userid(username))


class SessionAuthenticationPolicy(_SessionAuthenticationPolicy):
    def unauthenticated_userid(self, request):
        # If we're calling into this API on a request, then we want to register
        # a callback which will ensure that the response varies based on the
        # Cookie header.
        request.add_response_callback(add_vary_callback("Cookie"))

        # Dispatch to the real SessionAuthenticationPolicy
        return super().unauthenticated_userid(request)


@implementer(IAuthorizationPolicy)
class AccountTokenAuthorizationPolicy:
    def __init__(self, policy):
        self.policy = policy

    def permits(self, context, principals, permission):
        # The Pyramid API doesn't let us access the request here, so we have to
        # pull it out of the thread local instead.
        request = get_current_request()

        if request is None:
            return Denied("No active request.")

        # See if we have a macaroon
        account_token_service = request.find_service(IAccountTokenService, context=None)

        unverified_macaroon, account_token = (
            account_token_service.get_unverified_macaroon()
        )

        if unverified_macaroon is not None and account_token is not None:
            # Validate authorization properties of the macaroon
            try:
                verifier = Verifier()
                verifier.third_party_caveat_verifier_delegate = (
                    PassThroughThirdPartyCaveats()
                )

                verifier.satisfy_general(
                    self._validate_first_party_caveat_authorization
                )

                verifier.verify(unverified_macaroon, account_token.secret)

            except MacaroonException:
                return Denied("Invalid credentials")

        # The macaroon validated, so pass this on to the underlying
        # Authorization policies.
        return self.policy.permits(context, principals, permission)

    def principals_allowed_by_permission(self, context, permission):
        return self.policy.principals_allowed_by_permission(context, permission)

    def _validate_first_party_caveat_authorization(self, caveat):
        """Validate caveats relating to authorization."""
        # TODO: Decide on caveat language and implement authorization caveats
        # here (things like project name, project version, filename, hash, ...
        return True
