# SPDX-License-Identifier: Apache-2.0

import threading

import pretend
import pytest

from psycopg.errors import LockNotAvailable, UniqueViolation
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
        "jti": "buildkite-token-id",
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


@pytest.fixture
def publisher_service():
    return pretend.stub(jwt_identifier_exists=lambda jti: False)


class TestBuildkitePublisher:
    def test_properties(self):
        publisher = buildkite.BuildkitePublisher(
            organization_slug="acme",
            pipeline_slug="widgets",
            buildkite_organization_id=ORGANIZATION_ID,
            pipeline_id=PIPELINE_ID,
            build_branch="main",
            build_tag=None,
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
    def test_verify_claims(self, overrides, valid, publisher_service):
        publisher = buildkite.BuildkitePublisher(
            organization_slug="acme",
            pipeline_slug="widgets",
            buildkite_organization_id=ORGANIZATION_ID,
            pipeline_id=PIPELINE_ID,
            build_branch="main",
            build_tag=None,
            step_key="publish",
        )

        if valid:
            assert publisher.verify_claims(claims(**overrides), publisher_service)
        else:
            with pytest.raises(errors.InvalidPublisherError):
                publisher.verify_claims(claims(**overrides), publisher_service)

    @pytest.mark.parametrize("claim", ["build_branch", "build_tag", "step_key"])
    @pytest.mark.parametrize(
        ("configured", "signed_value", "present", "valid"),
        [
            (None, None, False, True),
            (None, None, True, True),
            (None, "release", True, True),
            ("release", "release", True, True),
            ("release", "other", True, False),
            ("release", None, True, False),
            ("release", None, False, False),
        ],
    )
    def test_optional_constraints(
        self,
        db_request,
        claim,
        configured,
        signed_value,
        present,
        valid,
        publisher_service,
    ):
        publisher = BuildkitePublisherFactory.create(
            organization_slug="acme",
            pipeline_slug="widgets",
            buildkite_organization_id=ORGANIZATION_ID,
            pipeline_id=PIPELINE_ID,
            **{claim: configured},
        )
        signed_claims = claims(**{claim: signed_value})
        if not present:
            signed_claims.pop(claim)

        if valid:
            assert publisher.verify_claims(signed_claims, publisher_service)
            assert (
                buildkite.BuildkitePublisher.lookup_by_claims(
                    db_request.db, signed_claims
                ).id
                == publisher.id
            )
        else:
            with pytest.raises(errors.InvalidPublisherError):
                publisher.verify_claims(signed_claims, publisher_service)
            with pytest.raises(errors.InvalidPublisherError):
                buildkite.BuildkitePublisher.lookup_by_claims(
                    db_request.db, signed_claims
                )

    @pytest.mark.parametrize(
        "publisher_class",
        [buildkite.BuildkitePublisher, buildkite.PendingBuildkitePublisher],
    )
    @pytest.mark.parametrize("claim", ["organization_id", "pipeline_id", "jti"])
    @pytest.mark.parametrize("value", [None, "", 123])
    def test_required_identity_claims(self, publisher_class, claim, value):
        signed_claims = claims(**{claim: value})
        with pytest.raises(errors.InvalidPublisherError, match=claim):
            publisher_class.check_claims_existence(signed_claims)

        signed_claims.pop(claim)
        with pytest.raises(errors.InvalidPublisherError, match=claim):
            publisher_class.check_claims_existence(signed_claims)

    @pytest.mark.parametrize(
        ("organization_id", "pipeline_id"),
        [
            (None, None),
            (ORGANIZATION_ID, None),
            (None, PIPELINE_ID),
        ],
    )
    def test_pins_unset_ids(self, organization_id, pipeline_id, publisher_service):
        publisher = buildkite.BuildkitePublisher(
            organization_slug="acme",
            pipeline_slug="widgets",
            buildkite_organization_id=organization_id,
            pipeline_id=pipeline_id,
            build_branch="main",
            build_tag=None,
            step_key="publish",
        )
        signed_claims = claims()

        buildkite.BuildkitePublisher.check_claims_existence(signed_claims)
        assert publisher.verify_claims(signed_claims, publisher_service)
        publisher.pin_claims(signed_claims)
        assert publisher.buildkite_organization_id == ORGANIZATION_ID
        assert publisher.pipeline_id == PIPELINE_ID

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
            build_branch=None,
            build_tag=None,
            step_key=None,
        )
        matching_publishers = {
            BuildkitePublisherFactory.create(
                organization_slug="acme",
                pipeline_slug="widgets",
                buildkite_organization_id=ORGANIZATION_ID,
                pipeline_id=PIPELINE_ID,
                build_branch=None,
                build_tag=None,
                step_key="publish",
            ).id,
            BuildkitePublisherFactory.create(
                organization_slug="acme",
                pipeline_slug="widgets",
                buildkite_organization_id=ORGANIZATION_ID,
                pipeline_id=PIPELINE_ID,
                build_branch="main",
                build_tag=None,
                step_key=None,
            ).id,
        }

        publisher = buildkite.BuildkitePublisher.lookup_by_claims(
            db_request.db, claims()
        )

        assert publisher.id in matching_publishers

    def test_lookup_unpinned_with_id_claims(self, db_request):
        publisher = BuildkitePublisherFactory.create(
            organization_slug="acme",
            pipeline_slug="widgets",
            buildkite_organization_id=None,
            pipeline_id=None,
        )
        signed_claims = claims()

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
                buildkite_organization_id=None,
                pipeline_id=None,
                build_branch="main",
                build_tag=None,
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
            buildkite_organization_id=None,
            pipeline_id=None,
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
            assert publisher.buildkite_organization_id is None
            assert publisher.pipeline_id is None
        assert pending in db_request.db.deleted


@pytest.mark.parametrize(
    "factory", [BuildkitePublisherFactory, PendingBuildkitePublisherFactory]
)
@pytest.mark.parametrize("build_branch", [None, "main"])
def test_null_constraints_do_not_allow_duplicates(db_request, factory, build_branch):
    fields = {
        "organization_slug": "acme",
        "pipeline_slug": "widgets",
        "build_branch": build_branch,
        "build_tag": None,
        "step_key": None,
    }
    factory.create(**fields)

    # A different restriction is still a distinct publisher.
    factory.create(**{**fields, "step_key": "publish"})

    with pytest.raises(UniqueViolation):
        factory.create(**fields)
