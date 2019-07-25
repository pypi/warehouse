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

from pyramid.authentication import CallbackAuthenticationPolicy
from pyramid.interfaces import IAuthenticationPolicy, IAuthorizationPolicy
from pyramid.security import Denied
from pyramid.threadlocal import get_current_request
from zope.interface import implementer

from warehouse.cache.http import add_vary_callback
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons.services import InvalidMacaroon


def extract_http_macaroon(request):
    """
    A helper function for the extraction of HTTP Macaroon from a given request.
    Returns either a ``None`` if no macaroon could be found, or the byte string
    that represents our Macaroon.
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        return None

    try:
        auth_method, auth = authorization.split(" ", 1)
    except ValueError:
        return None

    if auth_method.lower() != "macaroon":
        return None

    return auth


@implementer(IAuthenticationPolicy)
class MacaroonAuthenticationPolicy(CallbackAuthenticationPolicy):
    def __init__(self, callback=None):
        self.callback = callback

    def unauthenticated_userid(self, request):
        # If we're calling into this API on a request, then we want to register
        # a callback which will ensure that the response varies based on the
        # Authorization header.
        request.add_response_callback(add_vary_callback("Authorization"))

        # We need to extract our Macaroon from the request.
        macaroon = extract_http_macaroon(request)

        # Check to see if our Macaroon exists in the database, and if so
        # fetch the user that is associated with it.
        macaroon_service = request.find_service(IMacaroonService, context=None)
        return macaroon_service.find_userid(macaroon)

    def remember(self, request, userid, **kw):
        # This is a NO-OP because our Macaroon header policy doesn't allow
        # the ability for authentication to "remember" the user id. This
        # assumes it has been configured in clients somewhere out of band.
        return []

    def forget(self, request):
        # This is a NO-OP because our Macaroon header policy doesn't allow
        # the ability for authentication to "forget" the user id. This
        # assumes it has been configured in clients somewhere out of band.
        return []


@implementer(IAuthorizationPolicy)
class MacaroonAuthorizationPolicy:
    def __init__(self, policy):
        self.policy = policy

    def permits(self, context, principals, permission):
        # The Pyramid API doesn't let us access the request here, so we have to pull it
        # out of the thread local instead.
        # TODO: Work with Pyramid devs to figure out if there is a better way to support
        #       the worklow we are using hereor not.
        request = get_current_request()

        # Our request could possibly be a None, if there isn't an active request, in
        # that case we're going to always deny, because without a request, we can't
        # determine if this request is authorized or not.
        if request is None:
            return Denied("There was no active request.")

        # Re-extract our Macaroon from the request, it sucks to have to do this work
        # twice, but I believe it is inevitable unless we pass the Macaroon back as
        # a principal-- which doesn't seem to be the right fit for it.
        macaroon = extract_http_macaroon(request)

        # This logic will only happen on requests that are being authenticated with
        # Macaroons. Any other request will just fall back to the standard Authorization
        # policy.
        if macaroon is not None:
            macaroon_service = request.find_service(IMacaroonService, context=None)

            try:
                macaroon_service.verify(macaroon)
            except InvalidMacaroon as exc:
                return Denied(f"The supplied token was invalid: {str(exc)!r}")

        # If our Macaroon is verified, then we'll pass this request to our underlying
        # Authorization policy, so it can handle it's own authorization logic on
        # the prinicpal.
        return self.policy.permits(context, principals, permission)

    def principals_allowed_by_permission(self, context, permission):
        # We just dispatch this, because Macaroons don't restrict what principals are
        # allowed by a particular permission, they just restrict specific requests
        # to not have that permission.
        return self.policy.principals_allowed_by_permission(context, permission)
