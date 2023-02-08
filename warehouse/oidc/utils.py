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

from sqlalchemy.sql.expression import func, literal

from warehouse.events.tags import EventTag
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.models import (
    GitHubProvider,
    OIDCProvider,
    PendingGitHubProvider,
    PendingOIDCProvider,
)
from warehouse.packaging.models import JournalEntry, Project, Role

GITHUB_OIDC_ISSUER_URL = "https://token.actions.githubusercontent.com"

OIDC_ISSUER_URLS = {GITHUB_OIDC_ISSUER_URL}


def find_provider_by_issuer(
    session, issuer_url: str, signed_claims: SignedClaims, *, pending: bool = False
) -> OIDCProvider | PendingOIDCProvider | None:
    """
    Given an OIDC issuer URL and a dictionary of claims that have been verified
    for a token from that OIDC issuer, retrieve either an `OIDCProvider` registered
    to one or more projects or a `PendingOIDCProvider`, varying with the
    `pending` parameter.

    Returns `None` if no provider can be found.
    """

    if issuer_url not in OIDC_ISSUER_URLS:
        # This indicates a logic error, since we shouldn't have verified
        # claims for an issuer that we don't recognize and support.
        return None

    # This is the ugly part: OIDCProvider and PendingOIDCProvider are both
    # polymorphic, and retrieving the correct provider requires us to query
    # based on provider-specific claims.
    if issuer_url == GITHUB_OIDC_ISSUER_URL:
        repository = signed_claims["repository"]
        repository_owner, repository_name = repository.split("/", 1)
        workflow_prefix = f"{repository}/.github/workflows/"
        workflow_ref = signed_claims["job_workflow_ref"].removeprefix(workflow_prefix)

        provider_cls = GitHubProvider if not pending else PendingGitHubProvider

        return (
            session.query(provider_cls)
            .filter_by(
                repository_name=repository_name,
                repository_owner=repository_owner,
                repository_owner_id=signed_claims["repository_owner_id"],
            )
            .filter(
                literal(workflow_ref).like(
                    func.concat(provider_cls.workflow_filename, "%")
                )
            )
            .one_or_none()
        )
    else:
        # Unreachable; same logic error as above.
        return None  # pragma: no cover


def reify_pending_provider(
    session, pending_provider: PendingOIDCProvider, remote_addr: str
):
    """
    Reify a `PendingOIDCProvider` into an `OIDCProvider`, creating its
    project in the process.

    `remote_addr` is the IP address to attribute the changes to, in both the journal
    and event logs.

    Deletes the pending OIDC provider once complete.

    Returns the a tuple of the new project and new OIDC provider.
    """
    new_project = Project(name=pending_provider.project_name)
    session.add(new_project)

    session.add(
        JournalEntry(
            name=new_project.name,
            action="create",
            submitted_by=pending_provider.added_by,
            submitted_from=remote_addr,
        )
    )

    new_project.record_event(
        tag=EventTag.Project.ProjectCreate,
        ip_address=remote_addr,
        additional={"created_by": pending_provider.added_by.username},
    )

    session.add(
        Role(user=pending_provider.added_by, project=new_project, role_name="Owner")
    )

    session.add(
        JournalEntry(
            name=new_project.name,
            action=f"add Owner {pending_provider.added_by.username}",
            submitted_by=pending_provider.added_by,
            submitted_from=remote_addr,
        )
    )
    new_project.record_event(
        tag=EventTag.Project.RoleAdd,
        ip_address=remote_addr,
        additional={
            "submitted_by": pending_provider.added_by.username,
            "role_name": "Owner",
            "target_user": pending_provider.added_by.username,
        },
    )

    new_provider = pending_provider.reify(session)
    new_project.oidc_providers.append(new_provider)

    session.flush()

    return new_project, new_provider
