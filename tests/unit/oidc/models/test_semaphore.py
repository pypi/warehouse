# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.common.db.accounts import UserFactory
from warehouse.oidc import errors
from warehouse.oidc.models import semaphore


class TestSemaphorePublisher:
    def test_publisher_name(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        assert publisher.publisher_name == "SemaphoreCI"

    def test_publisher_base_url(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        assert publisher.publisher_base_url is None

    def test_publisher_url(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        assert publisher.publisher_url() is None
        assert publisher.publisher_url({"ref": "refs/heads/main"}) is None

    def test_stored_claims(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        assert publisher.stored_claims() == {"ref": None, "ref_type": None}
        assert publisher.stored_claims(
            {"ref": "refs/heads/main", "ref_type": "branch"}
        ) == {
            "ref": "refs/heads/main",
            "ref_type": "branch",
        }

    def test_sub(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        assert publisher.sub == "repo_slug:owner/repo"

    def test_repo_slug(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        assert publisher.repo_slug == "owner/repo"

    def test_repo(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        assert publisher.repo == "repo"

    def test_org(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        assert publisher.org == "example-org"

    def test_prj(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        assert publisher.prj == "example-project"

    def test_org_id(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        assert publisher.org_id == "org-id-1234"

    def test_prj_id(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        assert publisher.prj_id == "proj-id-5678"

    def test_stringifies_as_repository(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        assert str(publisher) == "owner/repo"

    def test_semaphore_publisher_admin_details(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        assert publisher.admin_details == [
            ("Organization", "example-org"),
            ("Organization ID", "org-id-1234"),
            ("Project", "example-project"),
            ("Project ID", "proj-id-5678"),
            ("Repository", "owner/repo"),
        ]

    def test_semaphore_publisher_all_known_claims(self):
        assert semaphore.SemaphorePublisher.all_known_claims() == {
            # verifiable claims
            "sub",
            "org",
            "org_id",
            "prj",
            "prj_id",
            "repo_slug",
            "jti",
            # preverified claims
            "iss",
            "iat",
            "nbf",
            "exp",
            "aud",
            # unchecked claims
            "repo",
            "wf_id",
            "ppl_id",
            "job_id",
            "branch",
            "pr_branch",
            "pr",
            "ref",
            "ref_type",
            "tag",
            "job_type",
            "trg",
            "sub127",
        }

    def test_semaphore_publisher_lookup_by_claims(self, db_request):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )
        db_request.db.add(publisher)
        db_request.db.flush()

        signed_claims = {
            "org": "example-org",
            "org_id": "org-id-1234",
            "prj": "example-project",
            "prj_id": "proj-id-5678",
            "repo_slug": "owner/repo",
        }

        found_publisher = semaphore.SemaphorePublisher.lookup_by_claims(
            db_request.db, signed_claims
        )

        assert found_publisher == publisher

    def test_semaphore_publisher_lookup_by_claims_not_found(self, db_request):
        signed_claims = {
            "org": "example-org",
            "org_id": "org-id-1234",
            "prj": "nonexistent-project",
            "prj_id": "proj-id-9999",
            "repo_slug": "owner/repo",
        }

        with pytest.raises(errors.InvalidPublisherError) as exc:
            semaphore.SemaphorePublisher.lookup_by_claims(db_request.db, signed_claims)

        assert str(exc.value) == "Publisher with matching claims was not found"

    def test_semaphore_publisher_lookup_missing_org(self, db_request):
        signed_claims = {
            "org_id": "org-id-1234",
            "prj": "example-project",
            "prj_id": "proj-id-5678",
            "repo_slug": "owner/repo",
        }

        with pytest.raises(errors.InvalidPublisherError) as exc:
            semaphore.SemaphorePublisher.lookup_by_claims(db_request.db, signed_claims)

        assert "Missing required claims" in str(exc.value)

    def test_semaphore_publisher_lookup_missing_prj(self, db_request):
        signed_claims = {
            "org": "example-org",
            "org_id": "org-id-1234",
            "prj_id": "proj-id-5678",
            "repo_slug": "owner/repo",
        }

        with pytest.raises(errors.InvalidPublisherError) as exc:
            semaphore.SemaphorePublisher.lookup_by_claims(db_request.db, signed_claims)

        assert "Missing required claims" in str(exc.value)

    def test_semaphore_publisher_lookup_missing_repo_slug(self, db_request):
        signed_claims = {
            "org": "example-org",
            "org_id": "org-id-1234",
            "prj": "example-project",
            "prj_id": "proj-id-5678",
        }

        with pytest.raises(errors.InvalidPublisherError) as exc:
            semaphore.SemaphorePublisher.lookup_by_claims(db_request.db, signed_claims)

        assert "Missing required claims" in str(exc.value)

    def test_semaphore_publisher_lookup_missing_org_id(self, db_request):
        signed_claims = {
            "org": "example-org",
            "prj": "example-project",
            "prj_id": "proj-id-5678",
            "repo_slug": "owner/repo",
        }

        with pytest.raises(errors.InvalidPublisherError) as exc:
            semaphore.SemaphorePublisher.lookup_by_claims(db_request.db, signed_claims)

        assert "Missing required claims" in str(exc.value)

    def test_semaphore_publisher_lookup_missing_prj_id(self, db_request):
        signed_claims = {
            "org": "example-org",
            "org_id": "org-id-1234",
            "prj": "example-project",
            "repo_slug": "owner/repo",
        }

        with pytest.raises(errors.InvalidPublisherError) as exc:
            semaphore.SemaphorePublisher.lookup_by_claims(db_request.db, signed_claims)

        assert "Missing required claims" in str(exc.value)

    def test_check_sub_valid(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        signed_claim = (
            "org:example-org:project:uuid-1234:repo:repo:"
            "ref_type:branch:ref:refs/heads/main"
        )
        assert semaphore._check_sub(
            publisher.repo_slug,
            signed_claim,
            {},
        )

    def test_check_sub_invalid(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        signed_claim = (
            "org:example-org:project:uuid-1234:repo:different-repo:"
            "ref_type:branch:ref:refs/heads/main"
        )
        assert not semaphore._check_sub(
            publisher.repo_slug,
            signed_claim,
            {},
        )

    def test_check_sub_missing_repo(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        signed_claim = "org:example-org:project:uuid-1234"
        assert not semaphore._check_sub(
            publisher.repo_slug,
            signed_claim,
            {},
        )

    def test_check_sub_empty_claim(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        assert not semaphore._check_sub(publisher.repo_slug, "", {})

    def test_check_sub_empty_repo_value(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        signed_claim = "org:example-org:project:uuid-1234:repo::ref_type:branch"
        assert not semaphore._check_sub(
            publisher.repo_slug,
            signed_claim,
            {},
        )

    def test_check_sub_only_repo_prefix(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        signed_claim = "org:example-org:project:uuid-1234:repo:"
        assert not semaphore._check_sub(
            publisher.repo_slug,
            signed_claim,
            {},
        )

    def test_check_sub_single_part_after_repo(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        signed_claim = "incomplete:repo:"
        assert not semaphore._check_sub(
            publisher.repo_slug,
            signed_claim,
            {},
        )

    def test_jti_property(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        assert publisher.jti == "placeholder"

    def test_attestation_identity(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )

        assert publisher.attestation_identity is None

    def test_exists_true(self, db_request):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="org-id-1234",
            project="example-project",
            semaphore_project_id="proj-id-5678",
            repo_slug="owner/repo",
        )
        db_request.db.add(publisher)
        db_request.db.flush()

        assert publisher.exists(db_request.db)


class TestPendingSemaphorePublisher:
    def test_reify(self, db_request):
        user = UserFactory.create()
        pending_publisher = semaphore.PendingSemaphorePublisher(
            organization="example-org",
            semaphore_organization_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            project="example-project",
            semaphore_project_id="b2c3d4e5-f6a7-8901-bcde-f01234567891",
            repo_slug="owner/repo",
            project_name="example-pypi-project",
            added_by_id=user.id,
        )

        db_request.db.add(pending_publisher)
        db_request.db.flush()

        publisher = pending_publisher.reify(db_request.db)

        assert isinstance(publisher, semaphore.SemaphorePublisher)
        assert publisher.organization == "example-org"
        assert (
            publisher.semaphore_organization_id
            == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        )
        assert publisher.project == "example-project"
        assert publisher.semaphore_project_id == "b2c3d4e5-f6a7-8901-bcde-f01234567891"
        assert publisher.repo_slug == "owner/repo"

        # The pending publisher should be deleted
        assert (
            db_request.db.query(semaphore.PendingSemaphorePublisher)
            .filter_by(id=pending_publisher.id)
            .count()
            == 0
        )

    def test_reify_existing_publisher(self, db_request):
        user = UserFactory.create()
        # Use matching IDs
        org_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        proj_id = "b2c3d4e5-f6a7-8901-bcde-f01234567891"

        existing_publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            semaphore_organization_id=org_id,
            project="example-project",
            semaphore_project_id=proj_id,
            repo_slug="owner/repo",
        )
        db_request.db.add(existing_publisher)
        db_request.db.flush()

        pending_publisher = semaphore.PendingSemaphorePublisher(
            organization="example-org",
            semaphore_organization_id=org_id,
            project="example-project",
            semaphore_project_id=proj_id,
            repo_slug="owner/repo",
            project_name="example-pypi-project",
            added_by_id=user.id,
        )
        db_request.db.add(pending_publisher)
        db_request.db.flush()

        publisher = pending_publisher.reify(db_request.db)

        assert publisher == existing_publisher

        # The pending publisher should be deleted
        assert (
            db_request.db.query(semaphore.PendingSemaphorePublisher)
            .filter_by(id=pending_publisher.id)
            .count()
            == 0
        )
