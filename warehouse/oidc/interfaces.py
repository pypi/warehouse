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

from __future__ import annotations

from typing import Any, NewType

from zope.interface import Interface

from warehouse.rate_limiting.interfaces import RateLimiterException

SignedClaims = NewType("SignedClaims", dict[str, Any])


class IOIDCProviderService(Interface):
    def verify_jwt_signature(unverified_token: str):
        """
        Verify the given JWT's signature, returning its signed claims if
        valid. If the signature is invalid, `None` is returned.

        This method does **not** verify the claim set itself -- the API
        consumer is responsible for evaluating the claim set.
        """
        pass

    def find_provider(signed_claims: SignedClaims):
        """
        Given a mapping of signed claims produced by `verify_jwt_signature`,
        attempt to find and return an `OIDCProvider` that matches them.

        If no `OIDCProvider` matches the claims, `None` is returned.
        """
        pass


class TooManyOIDCRegistrations(RateLimiterException):
    pass
