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

import base64

from pyramid.authorization import ACLHelper
from pyramid.interfaces import ISecurityPolicy
from zope.interface import implementer

from warehouse.accounts.interfaces import IUserService
from warehouse.accounts.utils import UserContext
from warehouse.authnz import Permissions
from warehouse.cache.http import add_vary_callback
from warehouse.errors import WarehouseDenied
from warehouse.macaroons import InvalidMacaroonError
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.metrics.interfaces import IMetricsService
from warehouse.oidc.utils import PublisherTokenContext
from warehouse.utils.security_policy import AuthenticationMethod, principals_for


def _extract_basic_macaroon(auth):
    """
    A helper function for extracting a macaroon from a
    HTTP Basic Authentication-style header.

    Returns None if the header doesn't contain a structurally
    valid macaroon, or the candidate (not yet verified) macaroon
    in a serialized form.
    """
    try:
        authorization = base64.b64decode(auth).decode()
        auth_method, _, auth = authorization.partition(":")
    except ValueError:
        return None

    if auth_method != "__token__":
        return None

    # Strip leading/trailing whitespace characters from the macaroon
    auth = auth.strip()

    return auth


def _extract_http_macaroon(request):
    """
    A helper function for the extraction of HTTP Macaroon from a given request.
    Returns either a None if no macaroon could be found, or the string
    that represents our serialized macaroon.
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        return None

    try:
        auth_method, auth = authorization.split(" ", 1)
    except ValueError:
        return None

    auth_method = auth_method.lower()

    metrics = request.find_service(IMetricsService, context=None)
    # TODO: As this is called in both `identity` and `permits`, we're going to
    #       end up double counting the metrics.
    metrics.increment("warehouse.macaroon.auth_method", tags=[f"method:{auth_method}"])

    if auth_method == "basic":
        return _extract_basic_macaroon(auth)
    elif auth_method in ["token", "bearer"]:
        return auth

    return None


@implementer(ISecurityPolicy)
class MacaroonSecurityPolicy:
    def __init__(self):
        self._acl = ACLHelper()

    def identity(self, request):
        # If we're calling into this API on a request, then we want to register
        # a callback which will ensure that the response varies based on the
        # Authorization header.
        request.add_response_callback(add_vary_callback("Authorization"))
        request.authentication_method = AuthenticationMethod.MACAROON

        # We need to extract our Macaroon from the request.
        macaroon = _extract_http_macaroon(request)
        if macaroon is None:
            return None

        # Check to see if our Macaroon exists in the database, and if so
        # fetch the user that is associated with it.
        macaroon_service = request.find_service(IMacaroonService, context=None)

        try:
            dm = macaroon_service.find_from_raw(macaroon)
            oidc_claims = (
                dm.additional.get("oidc")
                if dm.oidc_publisher and dm.additional
                else None
            )
        except InvalidMacaroonError:
            return None

        login_service = request.find_service(IUserService, context=None)

        # Every Macaroon is either associated with a user or an OIDC publisher.
        if dm.user is not None:
            is_disabled, _ = login_service.is_disabled(dm.user.id)
            if is_disabled:
                return None
            return UserContext(dm.user, dm)

        return PublisherTokenContext(dm.oidc_publisher, oidc_claims)

    def remember(self, request, userid, **kw):
        # This is a NO-OP because our Macaroon header policy doesn't allow
        # the ability for authentication to "remember" the user id. This
        # assumes it has been configured in clients somewhere out of band.
        return []

    def forget(self, request, **kw):
        # This is a NO-OP because our Macaroon header policy doesn't allow
        # the ability for authentication to "forget" the user id. This
        # assumes it has been configured in clients somewhere out of band.
        return []

    def authenticated_userid(self, request):
        # Handled by MultiSecurityPolicy
        raise NotImplementedError

    def permits(self, request, context, permission):
        # Re-extract our Macaroon from the request, it sucks to have to do this work
        # twice, but I believe it is inevitable unless we pass the Macaroon back as
        # a principal-- which doesn't seem to be the right fit for it.
        macaroon = _extract_http_macaroon(request)

        # It should not be possible to *not* have a macaroon at this point, because we
        # can't call this function without an identity that came from a macaroon
        assert isinstance(macaroon, str), "no valid macaroon"

        # Check to make sure that the permission we're attempting to permit is one that
        # is allowed to be used for macaroons.
        # TODO: This should be moved out of there and into the macaroons themselves, it
        #       doesn't really make a lot of sense here and it makes things more
        #       complicated if we want to allow the use of macaroons for actions other
        #       than uploading.
        if permission not in [
            Permissions.ProjectsUpload,
            # TODO: Adding API-specific routes here is not sustainable. However,
            #  removing this guard would allow Macaroons to be used for Session-based
            #  operations, bypassing any 2FA requirements.
            Permissions.APIEcho,
            Permissions.APIObservationsAdd,
        ]:
            return WarehouseDenied(
                f"API tokens are not valid for permission: {permission}!",
                reason="invalid_permission",
            )

        # Check if our macaroon itself is valid. This does not actually check if the
        # identity bound to that macaroon has permission to do what it's trying to do
        # but rather that the caveats embedded into the macaroon are valid for the given
        # request, context, and permission.
        macaroon_service = request.find_service(IMacaroonService, context=None)
        try:
            macaroon_service.verify(macaroon, request, context, permission)
        except InvalidMacaroonError as exc:
            return WarehouseDenied(
                f"Invalid API Token: {exc}", reason="invalid_api_token"
            )

        # The macaroon is valid, so we can actually see if request.identity is
        # authorized now or not.
        # NOTE: These parameters are in a different order than the signature of this
        #       method.
        return self._acl.permits(context, principals_for(request.identity), permission)
