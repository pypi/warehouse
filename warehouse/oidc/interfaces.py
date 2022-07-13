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
    def find_provider(unverified_token):
        """
        Verify the given JWT's signature and retrieve the OIDCProvider
        corresponding to its claims, verifying the claim set along the way.

        Returns None if the JWT's signature is invalid, if no corresponding
        OIDCProvider exists, or if the claims do not verify.
        """


class TooManyOIDCRegistrations(RateLimiterException):
    pass
