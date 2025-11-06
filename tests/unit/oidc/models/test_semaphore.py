# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.common.db.accounts import UserFactory
from warehouse.oidc import errors
from warehouse.oidc.models import semaphore


class TestSemaphorePublisher:
    def test_publisher_name(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-project"
        )

        assert publisher.publisher_name == "SemaphoreCI"

    def test_repository(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-project"
        )

        assert publisher.repository == "example-org/example-project"

    def test_publisher_base_url(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-project"
        )

        assert publisher.publisher_base_url is None

    def test_publisher_url(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-project"
        )

        assert publisher.publisher_url() is None
        assert publisher.publisher_url({"ref": "refs/heads/main"}) is None

    def test_stored_claims(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-project"
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
            organization="example-org", project="example-project"
        )

        assert publisher.sub == "repo:example-org/example-project"

    def test_repo_slug(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-project"
        )

        assert publisher.repo_slug == "example-org/example-project"

    def test_stringifies_as_repository(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-project"
        )

        assert str(publisher) == "example-org/example-project"

    def test_semaphore_publisher_admin_details(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-project"
        )

        assert publisher.admin_details == [
            ("Organization", "example-org"),
            ("Project", "example-project"),
        ]

    def test_semaphore_publisher_all_known_claims(self):
        assert semaphore.SemaphorePublisher.all_known_claims() == {
            # verifiable claims
            "sub",
            "repo_slug",
            "jti",
            # preverified claims
            "iss",
            "iat",
            "nbf",
            "exp",
            "aud",
            # unchecked claims
            "org",
            "org_id",
            "prj",
            "prj_id",
            "wf_id",
            "ppl_id",
            "job_id",
            "branch",
            "pr_branch",
            "pr",
            "ref",
            "ref_type",
            "tag",
            "repo",
            "job_type",
            "trg",
            "sub127",
        }

    def test_semaphore_publisher_lookup_by_claims(self, db_request):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-repo"
        )
        db_request.db.add(publisher)
        db_request.db.flush()

        signed_claims = {"repo_slug": "example-org/example-repo"}

        found_publisher = semaphore.SemaphorePublisher.lookup_by_claims(
            db_request.db, signed_claims
        )

        assert found_publisher == publisher

    def test_semaphore_publisher_lookup_by_claims_not_found(self, db_request):
        signed_claims = {"repo_slug": "example-org/nonexistent-repo"}

        with pytest.raises(errors.InvalidPublisherError) as exc:
            semaphore.SemaphorePublisher.lookup_by_claims(db_request.db, signed_claims)

        assert str(exc.value) == "Publisher with matching claims was not found"

    def test_semaphore_publisher_lookup_missing_repo_slug(self, db_request):
        signed_claims = {}

        with pytest.raises(errors.InvalidPublisherError) as exc:
            semaphore.SemaphorePublisher.lookup_by_claims(db_request.db, signed_claims)

        assert str(exc.value) == "Missing 'repo_slug' claim"

    def test_semaphore_publisher_lookup_invalid_repo_slug_format(self, db_request):
        signed_claims = {"repo_slug": "invalid-format"}

        with pytest.raises(errors.InvalidPublisherError) as exc:
            semaphore.SemaphorePublisher.lookup_by_claims(db_request.db, signed_claims)

        assert "Invalid 'repo_slug' claim format" in str(exc.value)

    def test_check_sub_valid(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-project"
        )

        signed_claim = (
            "org:example-org:project:uuid-1234:repo:example-org/example-project:"
            "ref_type:branch:ref:refs/heads/main"
        )
        assert semaphore._check_sub(
            publisher.repository,
            signed_claim,
            {},
        )

    def test_check_sub_invalid(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-project"
        )

        signed_claim = (
            "org:example-org:project:uuid-1234:repo:different-org/"
            "different-project:ref_type:branch:ref:refs/heads/main"
        )
        assert not semaphore._check_sub(
            publisher.repository,
            signed_claim,
            {},
        )

    def test_check_sub_missing_repo(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-project"
        )

        signed_claim = "org:example-org:project:uuid-1234"
        assert not semaphore._check_sub(
            publisher.repository,
            signed_claim,
            {},
        )

    def test_check_sub_empty_claim(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-project"
        )

        assert not semaphore._check_sub(publisher.repository, "", {})

    def test_check_sub_empty_repo_value(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-project"
        )

        signed_claim = "org:example-org:project:uuid-1234:repo::ref_type:branch"
        assert not semaphore._check_sub(
            publisher.repository,
            signed_claim,
            {},
        )

    def test_check_sub_only_repo_prefix(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-project"
        )

        signed_claim = "org:example-org:project:uuid-1234:repo:"
        assert not semaphore._check_sub(
            publisher.repository,
            signed_claim,
            {},
        )

    def test_check_sub_single_part_after_repo(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-project"
        )

        signed_claim = "incomplete:repo:"
        assert not semaphore._check_sub(
            publisher.repository,
            signed_claim,
            {},
        )

    def test_jti_property(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-project"
        )

        assert publisher.jti == "placeholder"

    def test_attestation_identity(self):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-project"
        )

        assert publisher.attestation_identity is None

    def test_exists_true(self, db_request):
        publisher = semaphore.SemaphorePublisher(
            organization="example-org", project="example-project"
        )
        db_request.db.add(publisher)
        db_request.db.flush()

        assert publisher.exists(db_request.db)


class TestPendingSemaphorePublisher:
    def test_reify(self, db_request):
        user = UserFactory.create()
        pending_publisher = semaphore.PendingSemaphorePublisher(
            organization="example-org",
            project="example-project",
            project_name="example-pypi-project",
            added_by_id=user.id,
        )

        db_request.db.add(pending_publisher)
        db_request.db.flush()

        publisher = pending_publisher.reify(db_request.db)

        assert isinstance(publisher, semaphore.SemaphorePublisher)
        assert publisher.organization == "example-org"
        assert publisher.project == "example-project"

        # The pending publisher should be deleted
        assert (
            db_request.db.query(semaphore.PendingSemaphorePublisher)
            .filter_by(id=pending_publisher.id)
            .count()
            == 0
        )

    def test_reify_existing_publisher(self, db_request):
        user = UserFactory.create()
        existing_publisher = semaphore.SemaphorePublisher(
            organization="example-org",
            project="example-project",
        )
        db_request.db.add(existing_publisher)
        db_request.db.flush()

        pending_publisher = semaphore.PendingSemaphorePublisher(
            organization="example-org",
            project="example-project",
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
