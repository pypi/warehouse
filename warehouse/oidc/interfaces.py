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


from zope.interface import Interface

from warehouse.rate_limiting.interfaces import RateLimiterException


class IOIDCProviderService(Interface):
    def get_key(key_id):
        """
        Return the JWK identified by the given KID,
        fetching it if not already cached locally.

        Returns None if the JWK does not exist or the access pattern is
        invalid (i.e., exceeds our internal limit on JWK requests to
        each provider).
        """
        pass

    def verify_signature_only(token):
        """
        Verify the given JWT's signature and basic claims, returning
        the decoded JWT, or `None` if invalid.

        This function **does not** verify the token's suitability
        for a particular action; subsequent checks on the decoded token's
        third party claims must be done to ensure that.
        """

    def verify_for_project(token, project):
        """
        Verify the given JWT's signature and basic claims in the same
        manner as `verify_signature_only`, but *also* verify that the JWT's
        claims are consistent with at least one of the project's registered
        OIDC providers.
        """


class TooManyOIDCRegistrations(RateLimiterException):
    pass
