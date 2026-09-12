# SPDX-License-Identifier: Apache-2.0

import threading

import pretend
import pytest

from psycopg.errors import LockNotAvailable
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.common.db.oidc import (
    BuildkitePublisherFactory,
    PendingBuildkitePublisherFactory,
)
from warehouse.oidc import errors
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

    @pytest.mark.parametrize(
        ("overrides", "valid"),
        [
            ({}, True),
            ({"sub": "different"}, True),
            ({"organization_id": "different"}, False),
            ({"pipeline_id": "different"}, False),
            ({"organization_slug": "different"}, False),
            ({"pipeline_slug": "different"}, False),
            ({"build_branch": "different"}, False),
            ({"step_key": None}, False),
        ],
    )
    def test_verify_claims(self, overrides, valid):
        publisher = buildkite.BuildkitePublisher(
            organization_slug="acme",
            pipeline_slug="widgets",
            buildkite_organization_id=ORGANIZATION_ID,
            pipeline_id=PIPELINE_ID,
            build_branch="main",
            build_tag="",
            step_key="publish",
        )

        if valid:
            assert publisher.verify_claims(claims(**overrides), pretend.stub())
        else:
            with pytest.raises(errors.InvalidPublisherError):
                publisher.verify_claims(claims(**overrides), pretend.stub())

    def test_unpinned_publisher_accepts_missing_ids(self):
        publisher = buildkite.BuildkitePublisher(
            organization_slug="acme",
            pipeline_slug="widgets",
            buildkite_organization_id="",
            pipeline_id="",
            build_branch="main",
            build_tag="",
            step_key="publish",
        )
        signed_claims = claims()
        signed_claims.pop("organization_id")
        signed_claims.pop("pipeline_id")

        buildkite.BuildkitePublisher.check_claims_existence(signed_claims)
        assert publisher.verify_claims(signed_claims, pretend.stub())
        publisher.pin_claims(signed_claims)
        assert publisher.buildkite_organization_id == ""
        assert publisher.pipeline_id == ""

    @pytest.mark.parametrize(
        ("present_claims", "expected_organization_id", "expected_pipeline_id"),
        [
            ({"organization_id"}, ORGANIZATION_ID, ""),
            ({"pipeline_id"}, "", PIPELINE_ID),
            ({"organization_id", "pipeline_id"}, ORGANIZATION_ID, PIPELINE_ID),
        ],
    )
    def test_unpinned_publisher_pins_present_ids(
        self, present_claims, expected_organization_id, expected_pipeline_id
    ):
        publisher = buildkite.BuildkitePublisher(
            organization_slug="acme",
            pipeline_slug="widgets",
            buildkite_organization_id="",
            pipeline_id="",
            build_branch="main",
            build_tag="",
            step_key="publish",
        )
        signed_claims = {
            claim: value
            for claim, value in claims().items()
            if claim not in {"organization_id", "pipeline_id"}
            or claim in present_claims
        }

        buildkite.BuildkitePublisher.check_claims_existence(signed_claims)
        assert publisher.verify_claims(signed_claims, pretend.stub())
        publisher.pin_claims(signed_claims)
        assert publisher.buildkite_organization_id == expected_organization_id
        assert publisher.pipeline_id == expected_pipeline_id

    @pytest.mark.parametrize(
        ("missing_claim", "error"),
        [
            ("organization_id", "--claim organization_id"),
            ("pipeline_id", "--claim pipeline_id"),
        ],
    )
    def test_pinned_publisher_rejects_missing_id(self, missing_claim, error):
        publisher = buildkite.BuildkitePublisher(
            organization_slug="acme",
            pipeline_slug="widgets",
            buildkite_organization_id=ORGANIZATION_ID,
            pipeline_id=PIPELINE_ID,
            build_branch="main",
            build_tag="",
            step_key="publish",
        )
        signed_claims = claims()
        signed_claims.pop(missing_claim)

        buildkite.BuildkitePublisher.check_claims_existence(signed_claims)
        with pytest.raises(errors.InvalidPublisherError, match=error):
            publisher.verify_claims(signed_claims, pretend.stub())

    def test_sub_is_required(self):
        signed_claims = claims()
        signed_claims.pop("sub")

        with pytest.raises(errors.InvalidPublisherError, match="Missing claim"):
            buildkite.BuildkitePublisher.check_claims_existence(signed_claims)

    @pytest.mark.parametrize("claim", ["build_tag", "step_key"])
    def test_nullable_claims_are_not_required(self, claim):
        signed_claims = claims()
        signed_claims.pop(claim, None)

        buildkite.BuildkitePublisher.check_claims_existence(signed_claims)

    def test_lookup_returns_a_matching_publisher(self, db_request):
        BuildkitePublisherFactory.create(
            organization_slug="acme",
            pipeline_slug="widgets",
            buildkite_organization_id=ORGANIZATION_ID,
            pipeline_id="00000000-0000-0000-0000-000000000000",
            build_branch="",
            build_tag="",
            step_key="",
        )
        matching_publishers = {
            BuildkitePublisherFactory.create(
                organization_slug="acme",
                pipeline_slug="widgets",
                buildkite_organization_id=ORGANIZATION_ID,
                pipeline_id=PIPELINE_ID,
                build_branch="",
                build_tag="",
                step_key="publish",
            ).id,
            BuildkitePublisherFactory.create(
                organization_slug="acme",
                pipeline_slug="widgets",
                buildkite_organization_id=ORGANIZATION_ID,
                pipeline_id=PIPELINE_ID,
                build_branch="main",
                build_tag="",
                step_key="",
            ).id,
        }

        publisher = buildkite.BuildkitePublisher.lookup_by_claims(
            db_request.db, claims()
        )

        assert publisher.id in matching_publishers

    def test_lookup_unpinned_without_id_claims(self, db_request):
        publisher = BuildkitePublisherFactory.create(
            organization_slug="acme",
            pipeline_slug="widgets",
            buildkite_organization_id="",
            pipeline_id="",
        )
        signed_claims = claims()
        signed_claims.pop("organization_id")
        signed_claims.pop("pipeline_id")

        assert (
            buildkite.BuildkitePublisher.lookup_by_claims(
                db_request.db, signed_claims
            ).id
            == publisher.id
        )

    def test_first_use_pinning_locks_publisher(self, app_config):
        engine = app_config.registry["sqlalchemy.engine"]
        with Session(engine) as session, session.begin():
            publisher = buildkite.BuildkitePublisher(
                organization_slug="locking-org",
                pipeline_slug="locking-pipeline",
                buildkite_organization_id="",
                pipeline_id="",
                build_branch="main",
                build_tag="",
                step_key="publish",
            )
            session.add(publisher)
            session.flush()
            publisher_id = publisher.id

        locked = threading.Event()
        release = threading.Event()
        thread_errors = []

        def pin_publisher():
            try:
                with Session(engine) as session, session.begin():
                    publisher = buildkite.BuildkitePublisher.lookup_by_claims(
                        session,
                        claims(
                            organization_slug="locking-org",
                            pipeline_slug="locking-pipeline",
                        ),
                    )
                    locked.set()
                    release.wait(timeout=5)
                    publisher.pin_claims(claims())
            except Exception as error:  # noqa: BLE001
                thread_errors.append(error)

        thread = threading.Thread(target=pin_publisher)
        thread.start()
        assert locked.wait(timeout=5)

        def lookup_while_locked():
            with Session(engine) as session, session.begin():
                session.execute(text("SET LOCAL lock_timeout = '100ms'"))
                buildkite.BuildkitePublisher.lookup_by_claims(
                    session,
                    claims(
                        organization_slug="locking-org",
                        pipeline_slug="locking-pipeline",
                    ),
                )

        try:
            with pytest.raises(LockNotAvailable, match="lock timeout"):
                lookup_while_locked()
        finally:
            release.set()
            thread.join(timeout=5)

        assert not thread.is_alive()
        assert thread_errors == []

        with Session(engine) as session, session.begin():
            with pytest.raises(errors.InvalidPublisherError, match="does not match"):
                buildkite.BuildkitePublisher.lookup_by_claims(
                    session,
                    claims(
                        organization_slug="locking-org",
                        pipeline_slug="locking-pipeline",
                        organization_id="different-organization",
                    ),
                )
            session.delete(session.get(buildkite.BuildkitePublisher, publisher_id))

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
