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

import enum

from pyramid.interfaces import ISecurityPolicy
from pyramid.request import RequestLocalCache
from pyramid.security import Denied
from zope.interface import implementer

from warehouse.accounts.utils import UserContext


# NOTE: Is there a better place for this to live? It may not even need to exist
#       since it's so small, it may be easier to just inline it.
def principals_for(identity) -> list[str]:
    if hasattr(identity, "__principals__"):
        return identity.__principals__()
    return []


class AuthenticationMethod(enum.Enum):
    BASIC_AUTH = "basic-auth"
    SESSION = "session"
    MACAROON = "macaroon"


@implementer(ISecurityPolicy)
class MultiSecurityPolicy:
    """
    A wrapper for multiple Pyramid 2.0-style "security policies", which replace
    Pyramid 1.0's separate AuthN and AuthZ APIs.

    Security policies are checked in the order provided during initialization,
    with the following semantics:

    * `identity`: Selected from the first policy to return non-`None`
    * `authenticated_userid`: Selected from the first policy to return an identity
    * `forget`: Combined from all policies
    * `remember`: Combined from all policies
    * `permits`: Uses the the policy that returned the identity.

    These semantics mostly mirror those of `pyramid-multiauth`.
    """

    def __init__(self, policies):
        self._policies = policies
        self._identity_cache = RequestLocalCache(self._get_identity_with_policy)

    def _get_identity_with_policy(self, request):
        # This will be cached per request, which means that we'll have a stable
        # result for both the identity AND the policy that produced it. Further
        # uses can then make sure to use the same policy throughout, at least
        # where it makes sense to.
        for policy in self._policies:
            if ident := policy.identity(request):
                return ident, policy

        return None, None

    def reset(self, request):
        self._identity_cache.clear(request)

    def identity(self, request):
        identity, _policy = self._identity_cache.get_or_create(request)
        return identity

    def authenticated_userid(self, request):
        if ident := self.identity(request):
            # TODO: Note, this logic breaks the contract of a SecurityPolicy, the
            #       authenticated_userid is intended to be used to fetch the unique
            #       identifier that represents the current identity. We're leaving
            #       it here for now, because there are a number of views directly
            #       using this to detect user vs not, which we'll need to move to a
            #       more correct pattern before fixing this.
            if isinstance(ident, UserContext):
                return str(ident.user.id)
        return None

    def forget(self, request, **kw):
        headers = []
        for policy in self._policies:
            headers.extend(policy.forget(request, **kw))
        return headers

    def remember(self, request, userid, **kw):
        headers = []
        for policy in self._policies:
            headers.extend(policy.remember(request, userid, **kw))
        return headers

    def permits(self, request, context, permission):
        identity, policy = self._identity_cache.get_or_create(request)
        # Sanity check that somehow our cached identity + policy didn't end up
        # different than what the request.identity is. This shouldn't be possible
        # but we'll assert it because if we let it pass silently it may mean that
        # some kind of confused-deputy attack is possible.
        assert request.identity == identity, "request has a different identity"

        # Dispatch to the underlying policy for the given identity, if there was one
        # for this request.
        if policy is not None:
            return policy.permits(request, context, permission)
        else:
            return Denied("unknown identity")
