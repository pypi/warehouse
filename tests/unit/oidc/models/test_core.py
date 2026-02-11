# SPDX-License-Identifier: Apache-2.0

import pretend
import psycopg
import pytest

from warehouse.accounts.models import User
from warehouse.oidc import errors
from warehouse.oidc.models import _core


def test_check_claim_binary():
    wrapped = _core.check_claim_binary(str.__eq__)

    assert wrapped("foo", "bar", pretend.stub()) is False
    assert wrapped("foo", "foo", pretend.stub()) is True


def test_check_claim_invariant():
    wrapped = _core.check_claim_invariant(True)
    assert wrapped(True, True, pretend.stub()) is True
    assert wrapped(False, True, pretend.stub()) is False

    wrapped = _core.check_claim_invariant(False)
    assert wrapped(False, False, pretend.stub()) is True
    assert wrapped(True, False, pretend.stub()) is False

    identity = object()
    wrapped = _core.check_claim_invariant(identity)
    assert wrapped(object(), object(), pretend.stub()) is False
    assert wrapped(identity, object(), pretend.stub()) is False
    assert wrapped(object(), identity, pretend.stub()) is False
    assert wrapped(identity, identity, pretend.stub()) is True


class TestPendingOIDCPublisher:
    def test_project_name_constraint(self, db_session):
        user = User(username="testuser", password="dummy-password", name="Test User")
        db_session.add(user)
        db_session.flush()

        invalid_project_name = "İnspect"
        publisher = _core.PendingOIDCPublisher(
            project_name=invalid_project_name,
            added_by_id=user.id,
        )
        db_session.add(publisher)
        with pytest.raises(psycopg.errors.CheckViolation):
            db_session.flush()

    def test_project_name_constraint_valid(self, db_session):
        user = User(
            username="testuser2",
            password="another-dummy-password",
            name="Another Test User",
        )
        db_session.add(user)
        db_session.flush()

        valid_project_name = "good-name_123"
        publisher = _core.PendingOIDCPublisher(
            project_name=valid_project_name,
            added_by_id=user.id,
        )
        db_session.add(publisher)
        db_session.flush()
        assert publisher.project_name == valid_project_name


class TestOIDCPublisher:
    def test_lookup_by_claims_raises(self):
        with pytest.raises(NotImplementedError):
            _core.OIDCPublisher.lookup_by_claims(pretend.stub(), pretend.stub())

    def test_oidc_publisher_not_default_verifiable(self):
        publisher = _core.OIDCPublisher(projects=[])

        with pytest.raises(errors.InvalidPublisherError) as e:
            publisher.check_claims_existence(signed_claims={})
        assert str(e.value) == "No required verifiable claims"

    def test_attestation_identity(self):
        publisher = _core.OIDCPublisher(projects=[])
        assert not publisher.attestation_identity

    def test_admin_details_default(self):
        publisher = _core.OIDCPublisher(projects=[])
        assert publisher.admin_details == []

    @pytest.mark.parametrize(
        ("url", "publisher_url", "expected"),
        [
            (  # GitHub trivial case
                "https://github.com/owner/project",
                "https://github.com/owner/project",
                True,
            ),
            (  # ActiveState trivial case
                "https://platform.activestate.com/owner/project",
                "https://platform.activestate.com/owner/project",
                True,
            ),
            (  # GitLab trivial case
                "https://gitlab.com/owner/project",
                "https://gitlab.com/owner/project",
                True,
            ),
            (
                # Google trivial case (no publisher URL)
                "https://example.com/owner/project",
                None,
                False,
            ),
            (  # URL is a sub-path of the TP URL
                "https://github.com/owner/project/issues",
                "https://github.com/owner/project",
                True,
            ),
            (  # Normalization
                "https://GiThUB.com/owner/project/",
                "https://github.com/owner/project",
                True,
            ),
            (  # TP URL is a prefix, but not a parent of the URL
                "https://github.com/owner/project22",
                "https://github.com/owner/project",
                False,
            ),
            (  # URL is a parent of the TP URL
                "https://github.com/owner",
                "https://github.com/owner/project",
                False,
            ),
            (  # Scheme component does not match
                "http://github.com/owner/project",
                "https://github.com/owner/project",
                False,
            ),
            (  # Host component does not match
                "https://gitlab.com/owner/project",
                "https://github.com/owner/project",
                False,
            ),
            (  # Host component matches, but contains user and port info
                "https://user@github.com:443/owner/project",
                "https://github.com/owner/project",
                False,
            ),
            (  # URL path component is empty
                "https://github.com",
                "https://github.com/owner/project",
                False,
            ),
            (  # TP URL path component is empty
                # (currently no TPs have an empty path, so even if the given URL is a
                # sub-path of the TP URL, we fail the verification)
                "https://github.com/owner/project",
                "https://github.com",
                False,
            ),
            (  # Both path components are empty
                # (currently no TPs have an empty path, so even if the given URL is the
                # same as the TP URL, we fail the verification)
                "https://github.com",
                "https://github.com",
                False,
            ),
            (  # Default verification is case-sensitive
                "https://publisher.com/owner/project",
                "https://publisher.com/owner/PrOjeCt",
                False,
            ),
        ],
    )
    def test_verify_url(self, monkeypatch, url, publisher_url, expected):
        class TestPublisher(_core.OIDCPublisher):
            __abstract__ = True

            @property
            def publisher_base_url(self):
                return publisher_url

        publisher = TestPublisher()
        assert publisher.verify_url(url) == expected


def test_check_existing_jti():
    publisher = pretend.stub(
        jwt_identifier_exists=pretend.call_recorder(lambda s: False),
    )

    assert _core.check_existing_jti(
        pretend.stub(),
        "6e67b1cb-2b8d-4be5-91cb-757edb2ec970",
        pretend.stub(),
        publisher_service=publisher,
    )


def test_check_existing_jti_fails(metrics):
    publisher = pretend.stub(
        jwt_identifier_exists=pretend.call_recorder(lambda s: True),
        metrics=metrics,
        publisher="fakepublisher",
    )
    with pytest.raises(errors.ReusedTokenError):
        assert _core.check_existing_jti(
            pretend.stub(),
            "6e67b1cb-2b8d-4be5-91cb-757edb2ec970",
            pretend.stub(),
            publisher_service=publisher,
        )

    assert (
        pretend.call("warehouse.oidc.reused_token", tags=["publisher:fakepublisher"])
        in metrics.increment.calls
    )
