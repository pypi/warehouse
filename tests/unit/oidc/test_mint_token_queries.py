# SPDX-License-Identifier: Apache-2.0

"""Regression test: mint_token should not lazy-load `project.users` per project."""

from tests.common.db.accounts import EmailFactory, UserFactory
from tests.common.db.ip_addresses import IpAddressFactory
from tests.common.db.oidc import GitHubPublisherFactory
from tests.common.db.packaging import ProjectFactory, RoleFactory
from warehouse.ip_addresses.models import IpAddress
from warehouse.oidc import views
from warehouse.oidc.models import GitHubPublisher

DUMMY_GITHUB_OIDC_JWT = "eyJ.fakeheader.fakebody.fakesig"


def test_mint_token_avoids_per_project_users_n_plus_one(
    mocker, db_request, query_recorder
):
    publisher = GitHubPublisherFactory(environment="prod")
    projects = []
    for _ in range(5):
        p = ProjectFactory.create()
        for j in range(3):
            u = UserFactory.create()
            EmailFactory.create(user=u, primary=True, verified=True)
            RoleFactory.create(
                user=u,
                project=p,
                role_name="Owner" if j < 2 else "Maintainer",
            )
        projects.append(p)
    publisher.projects = projects
    ip = IpAddressFactory.create()
    db_request.db.flush()
    publisher_id = publisher.id
    ip_id = ip.id
    # Detach so a subsequent load mirrors a fresh request — production loads
    # publisher fresh per request, and that load is what back-populates
    # `Project.oidc_publishers` and marks each project dirty.
    db_request.db.expunge_all()
    publisher = db_request.db.get(GitHubPublisher, publisher_id)
    # `record_event` reads `request.ip_address`; rebind it after expunge_all.
    db_request.ip_address = db_request.db.get(IpAddress, ip_id)

    claims = {
        "iss": "https://token.actions.githubusercontent.com",
        "ref": "r",
        "sha": "s",
        "environment": "prod",
    }
    oidc_service = mocker.Mock()
    oidc_service.verify_jwt_signature.return_value = claims
    oidc_service.find_publisher.side_effect = lambda c, pending=False: (
        None if pending else publisher
    )
    oidc_service.store_jwt_identifier.return_value = True

    with query_recorder:
        views.mint_token(oidc_service, DUMMY_GITHUB_OIDC_JWT, claims["iss"], db_request)
        db_request.db.flush()

    # The N+1 manifests as `Project.users` loaded per dirty project: a SELECT
    # joining roles, users, and user_emails. The selectinload pre-load should
    # mean it never appears here.
    queries = "\n".join(" ".join(q.lower().split()) for q in query_recorder.queries)
    assert "from roles, users left outer join user_emails" not in queries, (
        "Expected no per-project Project.users lazy-load during mint_token"
    )
