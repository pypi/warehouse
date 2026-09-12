# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.common.db.oidc import (
    BuildkitePublisherFactory,
    PendingBuildkitePublisherFactory,
)
from warehouse.oidc.models import buildkite

ORGANIZATION_ID = "00000000-1111-2222-3333-444444444444"
PIPELINE_ID = "11111111-2222-3333-4444-555555555555"


def claims(**overrides):
    values = {
        "iss": buildkite.BUILDKITE_OIDC_ISSUER_URL,
        "sub": (
            "organization:acme:pipeline:widgets:ref:refs/heads/main:"
            "commit:abc123:step:publish"
        ),
        "aud": "pypi",
        "iat": 1,
        "nbf": 1,
        "exp": 2,
        "organization_slug": "acme",
        "organization_id": ORGANIZATION_ID,
        "pipeline_slug": "widgets",
        "pipeline_id": PIPELINE_ID,
        "build_number": 42,
        "build_branch": "main",
        "build_commit": "abc123",
        "step_key": "publish",
        "job_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "agent_id": "ffffffff-1111-2222-3333-444444444444",
        "runner_environment": "buildkite-hosted",
        "build_source": "webhook",
    }
    values.update(overrides)
    return values


class TestBuildkitePublisher:
    def test_properties(self):
        publisher = buildkite.BuildkitePublisher(
            organization_slug="acme",
            pipeline_slug="widgets",
            buildkite_organization_id=ORGANIZATION_ID,
            pipeline_id=PIPELINE_ID,
            build_branch="main",
            build_tag="",
            step_key="publish",
        )

        assert publisher.publisher_name == "Buildkite"
        assert publisher.publisher_base_url == "https://buildkite.com/acme/widgets"
        assert publisher.publisher_url() == "https://buildkite.com/acme/widgets"
        assert (
            publisher.publisher_url(claims())
            == "https://buildkite.com/acme/widgets/builds/42"
            "#aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        )
        assert str(publisher) == "acme/widgets"
        assert publisher.admin_details == [
            ("Organization", "acme"),
            ("Pipeline", "widgets"),
            ("Organization ID", ORGANIZATION_ID),
            ("Pipeline ID", PIPELINE_ID),
            ("Build branch", "main"),
            ("Step key", "publish"),
        ]

    def test_stored_claims(self):
        publisher = BuildkitePublisherFactory.build()

        assert publisher.stored_claims(claims()) == {
            "build_number": 42,
            "build_branch": "main",
            "build_tag": None,
            "build_commit": "abc123",
            "step_key": "publish",
            "job_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        }

    @pytest.mark.parametrize("exists_in_db", [True, False])
    def test_exists(self, db_request, exists_in_db):
        publisher = BuildkitePublisherFactory.build()
        if exists_in_db:
            db_request.db.add(publisher)
            db_request.db.flush()

        assert publisher.exists(db_request.db) == exists_in_db


class TestPendingBuildkitePublisher:
    @pytest.mark.parametrize("existing", [True, False])
    def test_reify(self, db_request, existing):
        pending = PendingBuildkitePublisherFactory.create(
            organization_slug="acme",
            pipeline_slug="widgets",
            buildkite_organization_id="",
            pipeline_id="",
        )
        concrete = None
        if existing:
            concrete = BuildkitePublisherFactory.create(
                organization_slug=pending.organization_slug,
                pipeline_slug=pending.pipeline_slug,
                buildkite_organization_id=ORGANIZATION_ID,
                pipeline_id=PIPELINE_ID,
                build_branch=pending.build_branch,
                build_tag=pending.build_tag,
                step_key=pending.step_key,
            )

        publisher = pending.reify(db_request.db)

        if concrete:
            assert publisher.id == concrete.id
            assert publisher.buildkite_organization_id == ORGANIZATION_ID
            assert publisher.pipeline_id == PIPELINE_ID
        else:
            assert publisher.buildkite_organization_id == ""
            assert publisher.pipeline_id == ""
        assert pending in db_request.db.deleted
