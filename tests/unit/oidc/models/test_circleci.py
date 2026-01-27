# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.common.db.oidc import (
    CircleCIPublisherFactory,
    PendingCircleCIPublisherFactory,
)
from warehouse.oidc.errors import InvalidPublisherError
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.models.circleci import (
    CircleCIPublisher,
    _check_context_id,
    _check_optional_string,
)

ORG_ID = "00000000-0000-1000-8000-000000000001"
PROJECT_ID = "00000000-0000-1000-8000-000000000002"
PIPELINE_DEF_ID = "00000000-0000-1000-8000-000000000003"
CONTEXT_ID = "00000000-0000-1000-8000-000000000004"


VCS_REF = "refs/heads/main"
VCS_ORIGIN = "github.com/some-org/some-repo"


def new_signed_claims(
    org_id: str = ORG_ID,
    project_id: str = PROJECT_ID,
    pipeline_definition_id: str = PIPELINE_DEF_ID,
    context_ids: list[str] | None = None,
    ssh_rerun: bool = False,
    vcs_ref: str = VCS_REF,
    vcs_origin: str = VCS_ORIGIN,
) -> SignedClaims:
    claims = SignedClaims(
        {
            "oidc.circleci.com/org-id": org_id,
            "oidc.circleci.com/project-id": project_id,
            "oidc.circleci.com/context-ids": context_ids if context_ids else [],
            "oidc.circleci.com/job-id": "fake-job-id",
            "oidc.circleci.com/pipeline-definition-id": pipeline_definition_id,
            "oidc.circleci.com/pipeline-id": "fake-pipeline-id",
            "oidc.circleci.com/ssh-rerun": ssh_rerun,
            "oidc.circleci.com/vcs-ref": vcs_ref,
            "oidc.circleci.com/vcs-origin": vcs_origin,
            "oidc.circleci.com/workflow-id": "fake-workflow-id",
        }
    )
    return claims


class TestCheckContextId:
    def test_empty_ground_truth_always_passes(self):
        assert _check_context_id("", None, {}) is True
        assert _check_context_id("", [], {}) is True
        assert _check_context_id("", ["some-context"], {}) is True

    def test_required_context_fails_without_claim(self):
        assert _check_context_id("my-context", None, {}) is False
        assert _check_context_id("my-context", [], {}) is False

    def test_required_context_in_claim_array(self):
        assert _check_context_id("ctx-1", ["ctx-1", "ctx-2"], {}) is True
        assert _check_context_id("ctx-2", ["ctx-1", "ctx-2"], {}) is True

    def test_required_context_not_in_claim_array(self):
        assert _check_context_id("ctx-3", ["ctx-1", "ctx-2"], {}) is False


class TestCheckOptionalString:
    def test_empty_ground_truth_always_passes(self):
        assert _check_optional_string("", None, {}) is True
        assert _check_optional_string("", "", {}) is True
        assert _check_optional_string("", "some-value", {}) is True

    def test_required_value_fails_without_claim(self):
        assert _check_optional_string("required-value", None, {}) is False
        assert _check_optional_string("required-value", "", {}) is False

    def test_required_value_matches_claim(self):
        assert _check_optional_string("refs/heads/main", "refs/heads/main", {}) is True
        assert (
            _check_optional_string("github.com/org/repo", "github.com/org/repo", {})
            is True
        )

    def test_required_value_does_not_match_claim(self):
        assert (
            _check_optional_string("refs/heads/main", "refs/heads/develop", {}) is False
        )
        assert (
            _check_optional_string(
                "github.com/org/repo", "github.com/other-org/repo", {}
            )
            is False
        )


class TestCircleCIPublisher:
    def test_publisher_name(self):
        publisher = CircleCIPublisher()

        assert publisher.publisher_name == "CircleCI"

    def test_publisher_base_url(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
        )

        # CircleCI doesn't have a predictable public URL pattern
        assert publisher.publisher_base_url is None

    def test_publisher_url(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
        )

        assert publisher.publisher_url() is None

    def test_str(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
        )

        assert (
            str(publisher) == f"CircleCI project {PROJECT_ID} in organization {ORG_ID}"
        )

    def test_admin_details(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
        )

        assert publisher.admin_details == [
            ("Organization ID", ORG_ID),
            ("Project ID", PROJECT_ID),
            ("Pipeline Definition ID", PIPELINE_DEF_ID),
        ]

    def test_admin_details_with_context(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
            context_id=CONTEXT_ID,
        )

        assert publisher.admin_details == [
            ("Organization ID", ORG_ID),
            ("Project ID", PROJECT_ID),
            ("Pipeline Definition ID", PIPELINE_DEF_ID),
            ("Context ID", CONTEXT_ID),
        ]

    def test_admin_details_with_vcs_ref(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
            vcs_ref=VCS_REF,
        )

        assert publisher.admin_details == [
            ("Organization ID", ORG_ID),
            ("Project ID", PROJECT_ID),
            ("Pipeline Definition ID", PIPELINE_DEF_ID),
            ("VCS Ref", VCS_REF),
        ]

    def test_admin_details_with_vcs_origin(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
            vcs_origin=VCS_ORIGIN,
        )

        assert publisher.admin_details == [
            ("Organization ID", ORG_ID),
            ("Project ID", PROJECT_ID),
            ("Pipeline Definition ID", PIPELINE_DEF_ID),
            ("VCS Origin", VCS_ORIGIN),
        ]

    def test_admin_details_with_all_optional_fields(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
            context_id=CONTEXT_ID,
            vcs_ref=VCS_REF,
            vcs_origin=VCS_ORIGIN,
        )

        assert publisher.admin_details == [
            ("Organization ID", ORG_ID),
            ("Project ID", PROJECT_ID),
            ("Pipeline Definition ID", PIPELINE_DEF_ID),
            ("Context ID", CONTEXT_ID),
            ("VCS Ref", VCS_REF),
            ("VCS Origin", VCS_ORIGIN),
        ]

    def test_stored_claims(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
        )

        assert publisher.stored_claims() == {}
        assert publisher.stored_claims(new_signed_claims()) == {}

    def test_ssh_rerun_property(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
        )

        assert publisher.ssh_rerun is False

    def test_getattr_maps_claims_to_attributes(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
            context_id=CONTEXT_ID,
            vcs_ref=VCS_REF,
            vcs_origin=VCS_ORIGIN,
        )

        assert getattr(publisher, "oidc.circleci.com/org-id") == ORG_ID
        assert getattr(publisher, "oidc.circleci.com/project-id") == PROJECT_ID
        assert (
            getattr(publisher, "oidc.circleci.com/pipeline-definition-id")
            == PIPELINE_DEF_ID
        )
        assert getattr(publisher, "oidc.circleci.com/context-ids") == CONTEXT_ID
        assert getattr(publisher, "oidc.circleci.com/ssh-rerun") is False
        assert getattr(publisher, "oidc.circleci.com/vcs-ref") == VCS_REF
        assert getattr(publisher, "oidc.circleci.com/vcs-origin") == VCS_ORIGIN

    def test_getattr_raises_for_unknown_attribute(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
        )

        with pytest.raises(AttributeError, match="unknown_attribute"):
            getattr(publisher, "unknown_attribute")

    def test_ssh_rerun_claim_is_false(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
        )

        # The publisher expects ssh-rerun to always be False
        assert getattr(publisher, "oidc.circleci.com/ssh-rerun") is False

    def test_rejects_ssh_rerun_true(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
        )

        signed_claims = new_signed_claims(ssh_rerun=True)

        # Verify the ssh-rerun claim check fails when True
        check_fn = publisher.__required_verifiable_claims__[
            "oidc.circleci.com/ssh-rerun"
        ]
        assert check_fn(False, True, signed_claims) is False

    def test_accepts_ssh_rerun_false(self):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
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
            pipeline_definition_id=PIPELINE_DEF_ID,
        )

        signed_claims = new_signed_claims()

        assert (
            CircleCIPublisher.lookup_by_claims(db_request.db, signed_claims)
            == publisher
        )

    def test_lookup_by_claims_hits_with_context(self, db_request):
        publisher = CircleCIPublisherFactory.create(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
            context_id=CONTEXT_ID,
        )

        signed_claims = new_signed_claims(context_ids=[CONTEXT_ID, "other-context"])

        assert (
            CircleCIPublisher.lookup_by_claims(db_request.db, signed_claims)
            == publisher
        )

    def test_lookup_by_claims_falls_back_to_unconstrained(self, db_request):
        publisher = CircleCIPublisherFactory.create(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
            context_id="",
        )

        signed_claims = new_signed_claims(context_ids=["some-context-id"])

        assert (
            CircleCIPublisher.lookup_by_claims(db_request.db, signed_claims)
            == publisher
        )

    def test_lookup_by_claims_prefers_context_match(self, db_request):
        CircleCIPublisherFactory.create(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
            context_id="",
        )
        specific_publisher = CircleCIPublisherFactory.create(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
            context_id=CONTEXT_ID,
        )

        signed_claims = new_signed_claims(context_ids=[CONTEXT_ID])

        assert (
            CircleCIPublisher.lookup_by_claims(db_request.db, signed_claims)
            == specific_publisher
        )

    def test_lookup_by_claims_misses(self, db_request):
        CircleCIPublisherFactory.create(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
        )

        signed_claims = new_signed_claims(org_id="different-org-id")

        with pytest.raises(InvalidPublisherError):
            CircleCIPublisher.lookup_by_claims(db_request.db, signed_claims)

    @pytest.mark.parametrize("exists_in_db", [True, False])
    def test_exists(self, db_request, exists_in_db):
        publisher = CircleCIPublisher(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
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
            pipeline_definition_id=PIPELINE_DEF_ID,
            context_id=CONTEXT_ID,
            vcs_ref=VCS_REF,
            vcs_origin=VCS_ORIGIN,
        )

        publisher = pending.reify(db_request.db)

        assert isinstance(publisher, CircleCIPublisher)
        assert publisher.circleci_org_id == ORG_ID
        assert publisher.circleci_project_id == PROJECT_ID
        assert publisher.pipeline_definition_id == PIPELINE_DEF_ID
        assert publisher.context_id == CONTEXT_ID
        assert publisher.vcs_ref == VCS_REF
        assert publisher.vcs_origin == VCS_ORIGIN

    def test_reify_returns_existing_publisher(self, db_request):
        existing = CircleCIPublisherFactory.create(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
            context_id=CONTEXT_ID,
            vcs_ref=VCS_REF,
            vcs_origin=VCS_ORIGIN,
        )
        pending = PendingCircleCIPublisherFactory.create(
            circleci_org_id=ORG_ID,
            circleci_project_id=PROJECT_ID,
            pipeline_definition_id=PIPELINE_DEF_ID,
            context_id=CONTEXT_ID,
            vcs_ref=VCS_REF,
            vcs_origin=VCS_ORIGIN,
        )

        publisher = pending.reify(db_request.db)

        assert publisher == existing
