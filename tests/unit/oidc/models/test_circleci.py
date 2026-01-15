# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.common.db.oidc import (
    CircleCIPublisherFactory,
    PendingCircleCIPublisherFactory,
)
from warehouse.oidc.errors import InvalidPublisherError
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.models.circleci import CircleCIPublisher

ORG_ID = "00000000-0000-1000-8000-000000000001"
PROJECT_ID = "00000000-0000-1000-8000-000000000002"


def new_signed_claims(
    org_id: str = ORG_ID,
    project_id: str = PROJECT_ID,
    ssh_rerun: bool = False,
) -> SignedClaims:
    claims = SignedClaims(
        {
            "oidc.circleci.com/org-id": org_id,
            "oidc.circleci.com/project-id": project_id,
            "oidc.circleci.com/context-ids": [],
            "oidc.circleci.com/job-id": "fake-job-id",
            "oidc.circleci.com/pipeline-definition-id": "fake-pipeline-def-id",
            "oidc.circleci.com/pipeline-id": "fake-pipeline-id",
            "oidc.circleci.com/ssh-rerun": ssh_rerun,
            "oidc.circleci.com/vcs-ref": "refs/heads/main",
            "oidc.circleci.com/vcs-origin": "https://github.com/org/repo",
            "oidc.circleci.com/workflow-id": "fake-workflow-id",
        }
    )
    return claims


class TestCircleCIPublisher:
    def test_publisher_name(self):
        publisher = CircleCIPublisher()

        assert publisher.publisher_name == "CircleCI"

    def test_publisher_base_url(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID, circleci_project_id=PROJECT_ID
        )

        # CircleCI doesn't have a predictable public URL pattern
        assert publisher.publisher_base_url is None

    def test_publisher_url(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID, circleci_project_id=PROJECT_ID
        )

        assert publisher.publisher_url() is None

    def test_str(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID, circleci_project_id=PROJECT_ID
        )

        assert (
            str(publisher) == f"CircleCI project {PROJECT_ID} in organization {ORG_ID}"
        )

    def test_admin_details(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID, circleci_project_id=PROJECT_ID
        )

        assert publisher.admin_details == [
            ("Organization ID", ORG_ID),
            ("Project ID", PROJECT_ID),
        ]

    def test_stored_claims(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID, circleci_project_id=PROJECT_ID
        )

        assert publisher.stored_claims() == {}
        assert publisher.stored_claims(new_signed_claims()) == {}

    def test_ssh_rerun_property(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID, circleci_project_id=PROJECT_ID
        )

        assert publisher.ssh_rerun is False

    def test_getattr_maps_claims_to_attributes(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID, circleci_project_id=PROJECT_ID
        )

        assert getattr(publisher, "oidc.circleci.com/org-id") == ORG_ID
        assert getattr(publisher, "oidc.circleci.com/project-id") == PROJECT_ID
        assert getattr(publisher, "oidc.circleci.com/ssh-rerun") is False

    def test_getattr_raises_for_unknown_attribute(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID, circleci_project_id=PROJECT_ID
        )

        with pytest.raises(AttributeError, match="unknown_attribute"):
            getattr(publisher, "unknown_attribute")

    def test_ssh_rerun_claim_is_false(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID, circleci_project_id=PROJECT_ID
        )

        # The publisher expects ssh-rerun to always be False
        assert getattr(publisher, "oidc.circleci.com/ssh-rerun") is False

    def test_rejects_ssh_rerun_true(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID, circleci_project_id=PROJECT_ID
        )

        signed_claims = new_signed_claims(ssh_rerun=True)

        # Verify the ssh-rerun claim check fails when True
        check_fn = publisher.__required_verifiable_claims__[
            "oidc.circleci.com/ssh-rerun"
        ]
        assert check_fn(False, True, signed_claims) is False

    def test_accepts_ssh_rerun_false(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID, circleci_project_id=PROJECT_ID
        )

        signed_claims = new_signed_claims(ssh_rerun=False)

        # Verify the ssh-rerun claim check passes when False
        check_fn = publisher.__required_verifiable_claims__[
            "oidc.circleci.com/ssh-rerun"
        ]
        assert check_fn(False, False, signed_claims) is True

    def test_lookup_by_claims_hits(self, db_request):
        publisher = CircleCIPublisherFactory.create(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
        )

        signed_claims = new_signed_claims()

        assert (
            CircleCIPublisher.lookup_by_claims(db_request.db, signed_claims)
            == publisher
        )

    def test_lookup_by_claims_misses(self, db_request):
        CircleCIPublisherFactory.create(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
        )

        signed_claims = new_signed_claims(org_id="different-org-id")

        with pytest.raises(InvalidPublisherError):
            CircleCIPublisher.lookup_by_claims(db_request.db, signed_claims)

    @pytest.mark.parametrize("exists_in_db", [True, False])
    def test_exists(self, db_request, exists_in_db):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
        )

        if exists_in_db:
            db_request.db.add(publisher)
            db_request.db.flush()

        assert publisher.exists(db_request.db) == exists_in_db


class TestPendingCircleCIPublisher:
    def test_reify_creates_publisher(self, db_request):
        pending = PendingCircleCIPublisherFactory.create(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
        )

        publisher = pending.reify(db_request.db)

        assert isinstance(publisher, CircleCIPublisher)
        assert publisher.circleci_org_id == ORG_ID
        assert publisher.circleci_project_id == PROJECT_ID

    def test_reify_returns_existing_publisher(self, db_request):
        existing = CircleCIPublisherFactory.create(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
        )
        pending = PendingCircleCIPublisherFactory.create(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
        )

        publisher = pending.reify(db_request.db)

        assert publisher == existing
