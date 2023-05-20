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

from typing import TYPE_CHECKING, Any, NewType

from zope.interface import Interface

from warehouse.rate_limiting.interfaces import RateLimiterException

if TYPE_CHECKING:
    from warehouse.oidc.models import PendingOIDCPublisher
    from warehouse.packaging.models import Project

SignedClaims = NewType("SignedClaims", dict[str, Any])


class IOIDCPublisherService(Interface):
    def verify_jwt_signature(unverified_token: str):
        """
        Verify the given JWT's signature, returning its signed claims if
        valid. If the signature is invalid, `None` is returned.

        This method does **not** verify the claim set itself -- the API
        consumer is responsible for evaluating the claim set.
        """
        pass

    def find_publisher(signed_claims: SignedClaims, *, pending: bool = False):
        """
        Given a mapping of signed claims produced by `verify_jwt_signature`,
        attempt to find and return either a `OIDCPublisher` or `PendingOIDCPublisher`
        that matches them, depending on the value of `pending`.

        If no publisher matches the claims, `None` is returned.
        """
        pass

    def reify_pending_publisher(
        pending_publisher: PendingOIDCPublisher, project: Project
    ):
        """
        Reify the given pending `PendingOIDCPublisher` into an `OIDCPublisher`,
        adding it to the given project (presumed newly created) in the process.

        Returns the reified publisher.
        """
        pass


class TooManyOIDCRegistrations(RateLimiterException):
    pass
