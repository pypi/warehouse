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

from warehouse.oidc.models import (
    GitHubPublisher,
    GooglePublisher,
    PendingGitHubPublisher,
    PendingGooglePublisher,
)
from warehouse.oidc.models._core import OIDCPublisherMixin

GITHUB_OIDC_ISSUER_URL = "https://token.actions.githubusercontent.com"
GOOGLE_OIDC_ISSUER_URL = "https://accounts.google.com"

OIDC_ISSUER_URLS = {GITHUB_OIDC_ISSUER_URL, GOOGLE_OIDC_ISSUER_URL}

OIDC_PUBLISHER_CLASSES: dict[str, dict[bool, type[OIDCPublisherMixin]]] = {
    GITHUB_OIDC_ISSUER_URL: {False: GitHubPublisher, True: PendingGitHubPublisher},
    GOOGLE_OIDC_ISSUER_URL: {False: GooglePublisher, True: PendingGooglePublisher},
}


def find_publisher_by_issuer(session, issuer_url, signed_claims, *, pending=False):
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
        return None

    return publisher_cls.lookup_by_claims(session, signed_claims)
