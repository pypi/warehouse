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

import struct

from pymacaroons import Macaroon, Verifier
from pymacaroons.caveat_delegates import ThirdPartyCaveatVerifierDelegate
from pymacaroons.exceptions import MacaroonException

from pyramid.authentication import (
    BasicAuthAuthenticationPolicy as _BasicAuthAuthenticationPolicy,
    CallbackAuthenticationPolicy as _CallbackAuthenticationPolicy,
    SessionAuthenticationPolicy as _SessionAuthenticationPolicy,
)

from warehouse.accounts.interfaces import IUserService
from warehouse.cache.http import add_vary_callback


class AccountTokenAuthenticationPolicy(_CallbackAuthenticationPolicy):
    def __init__(self, authenticate):
        self._authenticate = authenticate
        self.callback = self._auth_callback

        self._routes_allowed = ["forklift.legacy.file_upload"]

    def unauthenticated_userid(self, request):
        if request.matched_route.name not in self._routes_allowed:
            return None

        account_token = request.params.get("account_token")

        if account_token is None:
            return None

        try:
            macaroon = Macaroon.deserialize(account_token)

            # First, check identifier and location
            if macaroon.identifier != request.registry.settings["account_token.id"]:
                return None

            if macaroon.location != "pypi.org":
                return None

            # Check the macaroon against our configuration
            verifier = Verifier()

            verifier.third_party_caveat_verifier_delegate = IgnoreThirdPartyCaveats()

            verifier.satisfy_general(self._validate_first_party_caveat)

            verified = verifier.verify(
                macaroon, request.registry.settings["account_token.secret"]
            )

            if verified:
                # Get id from token
                account_token_id = None
                package = None

                for each in macaroon.first_party_caveats():
                    caveat = each.to_dict()
                    caveat_parts = caveat["cid"].split(": ")
                    caveat_key = caveat_parts[0]
                    caveat_value = ": ".join(caveat_parts[1:])

                    # If caveats are specified multiple times, only trust the
                    # first value we encounter.
                    if caveat_key == "id" and account_token_id is None:
                        account_token_id = caveat_value

                    elif caveat_key == "package" and package is None:
                        package = caveat_value

                if package is not None:
                    request.session["account_token_package"] = package

                if account_token_id is not None:
                    login_service = request.find_service(IUserService, context=None)

                    return login_service.find_userid_by_account_token(account_token_id)

        except (struct.error, MacaroonException) as e:
            return None

    def remember(self, request, userid, **kw):
        """A no-op. Let other authenticators handle this."""
        return []

    def forget(self, request):
        """ A no-op. Let other authenticators handle this."""
        return []

    def _validate_first_party_caveat(self, caveat):
        # Only support 'id' and 'package' caveat for now
        if caveat.split(": ")[0] not in ["id", "package"]:
            return False

        return True

    def _auth_callback(self, userid, request):
        return self._authenticate(userid, request)


class IgnoreThirdPartyCaveats(ThirdPartyCaveatVerifierDelegate):
    def verify_third_party_caveat(self, *args, **kwargs):
        return True


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
