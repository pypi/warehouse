# SPDX-License-Identifier: Apache-2.0

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
