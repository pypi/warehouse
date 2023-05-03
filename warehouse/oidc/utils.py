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

from sqlalchemy import or_
from sqlalchemy.sql.expression import func, literal

from warehouse.oidc.models import (
    GitHubPublisher,
    GooglePublisher,
    PendingGitHubPublisher,
    PendingGooglePublisher,
)

GITHUB_OIDC_ISSUER_URL = "https://token.actions.githubusercontent.com"
GOOGLE_OIDC_ISSUER_URL = "https://accounts.google.com"

OIDC_ISSUER_URLS = {GITHUB_OIDC_ISSUER_URL, GOOGLE_OIDC_ISSUER_URL}


def find_publisher_by_issuer(session, issuer_url, signed_claims, *, pending=False):
    """
    Given an OIDC issuer URL and a dictionary of claims that have been verified
    for a token from that OIDC issuer, retrieve either an `OIDCPublisher` registered
    to one or more projects or a `PendingOIDCPublisher`, varying with the
    `pending` parameter.

    Returns `None` if no publisher can be found.
    """

    if issuer_url not in OIDC_ISSUER_URLS:
        # This indicates a logic error, since we shouldn't have verified
        # claims for an issuer that we don't recognize and support.
        return None

    # This is the ugly part: OIDCPublisher and PendingOIDCPublisher are both
    # polymorphic, and retrieving the correct publisher requires us to query
    # based on publisher-specific claims.
    if issuer_url == GITHUB_OIDC_ISSUER_URL:
        return _find_github_publisher(session, signed_claims, pending=pending)
    elif issuer_url == GOOGLE_OIDC_ISSUER_URL:
        return _find_google_publisher(session, signed_claims, pending=pending)
    else:
        # Unreachable; same logic error as above.
        return None  # pragma: no cover


def _find_github_publisher(session, signed_claims, *, pending=False):
    repository = signed_claims["repository"]
    repository_owner, repository_name = repository.split("/", 1)
    workflow_prefix = f"{repository}/.github/workflows/"
    workflow_ref = signed_claims["job_workflow_ref"].removeprefix(workflow_prefix)

    publisher_cls = GitHubPublisher if not pending else PendingGitHubPublisher

    publisher = None
    # If an environment exists in the claim set, try finding a publisher
    # that matches the provided environment first.
    if environment := signed_claims.get("environment"):
        publisher = (
            session.query(publisher_cls)
            .filter_by(
                repository_name=repository_name,
                repository_owner=repository_owner,
                repository_owner_id=signed_claims["repository_owner_id"],
                environment=environment,
            )
            .filter(
                literal(workflow_ref).like(
                    func.concat(publisher_cls.workflow_filename, "%")
                )
            )
            .one_or_none()
        )

    # There are no publishers for that specific environment, try finding a
    # publisher without a restriction on the environment
    if not publisher:
        publisher = (
            session.query(publisher_cls)
            .filter_by(
                repository_name=repository_name,
                repository_owner=repository_owner,
                repository_owner_id=signed_claims["repository_owner_id"],
                environment=None,
            )
            .filter(
                literal(workflow_ref).like(
                    func.concat(publisher_cls.workflow_filename, "%")
                )
            )
            .one_or_none()
        )

    return publisher


def _find_google_publisher(session, signed_claims, *, pending=False):
    publisher_cls = GooglePublisher if not pending else PendingGooglePublisher

    # The `sub` claim should always be present in the claim set, but is
    # optional on the registered publisher side. We first check for a
    # publisher that has both, and then for one with no `sub`.
    # This has to happen as separate queries to prevent duplicate
    # results: both variants can be registered, and we always want
    # to return the more specialized one if possible.
    publisher = (
        session.query(publisher_cls)
        .filter_by(email=signed_claims["email"], sub=signed_claims["sub"])
        .one_or_none()
    )

    if publisher is not None:
        return publisher

    return (
        session.query(publisher_cls)
        .filter_by(email=signed_claims["email"], sub=None)
        .one_or_none()
    )
