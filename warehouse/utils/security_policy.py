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

from zope.interface import implementer

from pyramid.interfaces import ISecurityPolicy


@implementer(ISecurityPolicy)
class MultiSecurityPolicy:
    """
    A wrapper for multiple Pyramid 2.0-style "security policies", which replace
    Pyramid 1.0's separate AuthN and AuthZ APIs.

    Security policies are checked in the order provided during initialization,
    with the following semantics:

    * `identity`: Selected from the first policy to return non-`None`
    * `authenticated_userid`: Selected from the effective policy
    * `forget`: Selected from the effective policy
    * `remember`: Selected from the effective policy
    * `permits`: Uses the provided `authz` object, which must provide a `permits` API

    These semantics are notably different from `pyramid_multiauth`, which
    combines all headers from all policies to form its wrapped versions of
    `forget` and `remember`.

    They're also a slight deviation from the expected Pyramid 2.0 policy APIs:
    instead of taking `permits` from the effective policy, we supply it via
    the constructor. We do this because Warehouse has multiple authentication
    mechanisms but only one authorization mechanism, so it doesn't make sense
    to plumb that mechanism separately though each policy.
    """
    def __init__(self, policies, authz):
        self._policies = policies
        self._authz = authz

        # We set this once we know which policy is effective.
        # NOTE: This could alternatively be something like a "FailSafePolicy",
        # which returns a bunch of reasonable defaults (deny all, etc).
        self._effective_policy = None

    def identity(self, request):
        for policy in self._policies:
            if ident := policy.identity(request):
                self._effective_policy = policy
                return ident

        return None

    def authenticated_userid(self, request):
        return self.request.identity.id

    def forget(self, **kw):
        return self._effective_policy.forget(**kw)

    def remember(self, **kw):
        return self._effective_policy.remember(**kw)

    def permits(self, context, permission):
        return self._authz.permits(context, permission)
