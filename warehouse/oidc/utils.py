# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing

from dataclasses import dataclass

from pyramid.authorization import Authenticated

from warehouse.admin.flags import AdminFlagValue
from warehouse.oidc.errors import InvalidPublisherError
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.models import (
    ACTIVESTATE_OIDC_ISSUER_URL,
    GITHUB_OIDC_ISSUER_URL,
    GITLAB_OIDC_ISSUER_URL,
    GOOGLE_OIDC_ISSUER_URL,
    ActiveStatePublisher,
    GitHubPublisher,
    GitLabPublisher,
    GooglePublisher,
    OIDCPublisher,
    PendingActiveStatePublisher,
    PendingGitHubPublisher,
    PendingGitLabPublisher,
    PendingGooglePublisher,
    PendingOIDCPublisher,
)

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session


OIDC_ISSUER_SERVICE_NAMES = {
    GITHUB_OIDC_ISSUER_URL: "github",
    GITLAB_OIDC_ISSUER_URL: "gitlab",
    GOOGLE_OIDC_ISSUER_URL: "google",
    ACTIVESTATE_OIDC_ISSUER_URL: "activestate",
}

OIDC_ISSUER_ADMIN_FLAGS = {
    GITHUB_OIDC_ISSUER_URL: AdminFlagValue.DISALLOW_GITHUB_OIDC,
    GITLAB_OIDC_ISSUER_URL: AdminFlagValue.DISALLOW_GITLAB_OIDC,
    GOOGLE_OIDC_ISSUER_URL: AdminFlagValue.DISALLOW_GOOGLE_OIDC,
    ACTIVESTATE_OIDC_ISSUER_URL: AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC,
}

OIDC_PUBLISHER_CLASSES: dict[
    str, dict[bool, type[OIDCPublisher | PendingOIDCPublisher]]
] = {
    GITHUB_OIDC_ISSUER_URL: {False: GitHubPublisher, True: PendingGitHubPublisher},
    GITLAB_OIDC_ISSUER_URL: {False: GitLabPublisher, True: PendingGitLabPublisher},
    GOOGLE_OIDC_ISSUER_URL: {False: GooglePublisher, True: PendingGooglePublisher},
    ACTIVESTATE_OIDC_ISSUER_URL: {
        False: ActiveStatePublisher,
        True: PendingActiveStatePublisher,
    },
}


def find_publisher_by_issuer(
    session: Session,
    issuer_url: str,
    signed_claims: SignedClaims,
    *,
    pending: bool = False,
) -> OIDCPublisher | PendingOIDCPublisher:
    """
    Given an OIDC issuer URL and a dictionary of claims that have been verified
    for a token from that OIDC issuer, retrieve either an `OIDCPublisher` registered
    to one or more projects or a `PendingOIDCPublisher`, varying with the
    `pending` parameter.

    Returns `None` if no publisher can be found.
    """

    try:
        publisher_cls = OIDC_PUBLISHER_CLASSES[issuer_url][pending]
    except KeyError:
        # This indicates a logic error, since we shouldn't have verified
        # claims for an issuer that we don't recognize and support.
        raise InvalidPublisherError(f"Issuer {issuer_url!r} is unsupported")

    # Before looking up the publisher by claims, we need to ensure that all expected
    # claims are present in the JWT.
    publisher_cls.check_claims_existence(signed_claims)

    return publisher_cls.lookup_by_claims(session, signed_claims)


@dataclass
class PublisherTokenContext:
    """
    This class supports `MacaroonSecurityPolicy` in
    `warehouse.macaroons.security_policy`.

    It is a wrapper containing both the signed claims associated with an OIDC
    authenticated request and its `OIDCPublisher` DB model. We use it to smuggle
    claims from the identity provider through to a session. `request.identity`
    in an OIDC authenticated request should return this type.
    """

    publisher: OIDCPublisher
    """
    The associated OIDC publisher.
    """

    claims: SignedClaims | None
    """
    Pertinent OIDC claims from the token, if they exist.
    """

    def __principals__(self) -> list[str]:
        return [Authenticated, f"oidc:{self.publisher.id}"]
