# SPDX-License-Identifier: Apache-2.0

import psycopg
import pytest

from tests.common.db.oidc import PendingGitHubPublisherFactory
from warehouse.oidc import errors
from warehouse.oidc.models import _core
from warehouse.oidc.services import OIDCPublisherService


def test_check_claim_binary(mocker):
    wrapped = _core.check_claim_binary(str.__eq__)

    assert wrapped("foo", "bar", mocker.sentinel.all_signed_claims) is False
    assert wrapped("foo", "foo", mocker.sentinel.all_signed_claims) is True


def test_check_claim_invariant(mocker):
    wrapped = _core.check_claim_invariant(True)
    assert wrapped(True, True, mocker.sentinel.all_signed_claims) is True
    assert wrapped(False, True, mocker.sentinel.all_signed_claims) is False

    wrapped = _core.check_claim_invariant(False)
    assert wrapped(False, False, mocker.sentinel.all_signed_claims) is True
    assert wrapped(True, False, mocker.sentinel.all_signed_claims) is False

    identity = object()
    wrapped = _core.check_claim_invariant(identity)
    assert wrapped(object(), object(), mocker.sentinel.all_signed_claims) is False
    assert wrapped(identity, object(), mocker.sentinel.all_signed_claims) is False
    assert wrapped(object(), identity, mocker.sentinel.all_signed_claims) is False
    assert wrapped(identity, identity, mocker.sentinel.all_signed_claims) is True


class TestPendingOIDCPublisher:
    def test_project_name_constraint(self, db_session):
        invalid_project_name = "İnspect"

        with pytest.raises(psycopg.errors.CheckViolation):
            PendingGitHubPublisherFactory(project_name=invalid_project_name)

    def test_project_name_constraint_valid(self, db_session):
        valid_project_name = "good-name_123"
        publisher = PendingGitHubPublisherFactory(project_name=valid_project_name)

        assert publisher.project_name == valid_project_name


class TestOIDCPublisher:
    def test_lookup_by_claims_raises(self, mocker):
        with pytest.raises(NotImplementedError):
            _core.OIDCPublisher.lookup_by_claims(
                mocker.sentinel.session, mocker.sentinel.signed_claims
            )

    def test_oidc_publisher_not_default_verifiable(self):
        publisher = _core.OIDCPublisher(projects=[])

        with pytest.raises(errors.InvalidPublisherError) as e:
            publisher.check_claims_existence(signed_claims={})
        assert str(e.value) == "No required verifiable claims"

    def test_check_claims_existence_with_prefixed_claims(self, mocker):
        class TestPrefixedPublisher(_core.OIDCPublisher):
            __abstract__ = True
            __required_verifiable_claims__ = {
                "required_claim": mocker.stub(name="required_claim_check")
            }
            __unchecked_prefixed_claims__ = {"custom_"}

        sentry_sdk = mocker.patch.object(_core, "sentry_sdk", autospec=True)

        signed_claims = {
            "required_claim": "value",
            "custom_foo": "bar",
            "custom_123": "baz",
        }
        TestPrefixedPublisher.check_claims_existence(signed_claims)
        sentry_sdk.capture_message.assert_not_called()

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
    def test_verify_url(self, url, publisher_url, expected):
        class TestPublisher(_core.OIDCPublisher):
            __abstract__ = True

            @property
            def publisher_base_url(self):
                return publisher_url

        publisher = TestPublisher()
        assert publisher.verify_url(url) == expected


def test_check_existing_jti(mocker):
    service = mocker.create_autospec(OIDCPublisherService, instance=True)
    service.jwt_identifier_exists.return_value = False

    assert _core.check_existing_jti(
        mocker.sentinel.ground_truth,
        "6e67b1cb-2b8d-4be5-91cb-757edb2ec970",
        mocker.sentinel.all_signed_claims,
        publisher_service=service,
    )


def test_check_existing_jti_fails(mocker, metrics):
    service = mocker.create_autospec(OIDCPublisherService, instance=True)
    service.jwt_identifier_exists.return_value = True
    service.metrics = metrics
    service.publisher = "fakepublisher"

    with pytest.raises(errors.ReusedTokenError):
        _core.check_existing_jti(
            mocker.sentinel.ground_truth,
            "6e67b1cb-2b8d-4be5-91cb-757edb2ec970",
            mocker.sentinel.all_signed_claims,
            publisher_service=service,
        )

    metrics.increment.assert_called_once_with(
        "warehouse.oidc.reused_token", tags=["publisher:fakepublisher"]
    )
