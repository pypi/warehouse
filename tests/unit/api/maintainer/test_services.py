# SPDX-License-Identifier: Apache-2.0

import datetime as dt
import hashlib

import psycopg
import pytest

from sqlalchemy import select
from zope.interface.verify import verifyClass

from warehouse.api.maintainer import (
    ApiKey,
    ApiKeyLimitError,
    ApiKeyNameInUseError,
    ApiKeyScope,
    IApiKeyService,
    InvalidApiKeyError,
    _services as services,
)
from warehouse.utils import now

from ....common.db.accounts import UserFactory
from ....common.db.maintainer_api import ApiKeyFactory


def _in_days(days):
    return now() + dt.timedelta(days=days)


def test_generate_api_key_format():
    raw_key = services.generate_api_key()

    assert raw_key.startswith("pypi_mapi_v1_")
    assert len(raw_key) == 13 + 30 + 6
    assert services.is_well_formed(raw_key)


def test_checksum_is_stable():
    """Changing the checksum would reject every key already issued."""
    assert services.is_well_formed("pypi_mapi_v1_iImvJkcnHed1UwODqqDOeTk9reZXfJ1lAZKj")


def test_base62_pads_small_values():
    assert services._base62(0) == "000000"
    assert services._base62(61) == "00000z"


@pytest.mark.parametrize(
    "raw_key",
    [
        pytest.param("", id="empty"),
        pytest.param("pypi-AgEIcHlwaS5vcmc", id="API token"),
        pytest.param("pypi_mapi_v1_" + "a" * 35, id="too short"),
        pytest.param("pypi_mapi_v1_" + "a" * 37, id="too long"),
        pytest.param("pypi_mapi_v1_" + "a" * 35 + "_", id="bad alphabet"),
        pytest.param("pypi_mapi_v2_" + "a" * 36, id="unknown version"),
    ],
)
def test_is_well_formed_rejects_bad_shape(raw_key):
    assert not services.is_well_formed(raw_key)


def test_is_well_formed_rejects_typo():
    raw_key = services.generate_api_key()
    swapped = "b" if raw_key[20] == "a" else "a"
    typo = raw_key[:20] + swapped + raw_key[21:]

    assert not services.is_well_formed(typo)


def test_hash_api_key():
    assert services.hash_api_key("pypi_mapi_v1_abc") == (
        hashlib.sha256(b"pypi_mapi_v1_abc").hexdigest()
    )


class TestDatabaseApiKeyService:
    def test_verify_class(self):
        assert verifyClass(IApiKeyService, services.DatabaseApiKeyService)

    def test_factory(self, db_request):
        service = services.database_api_key_factory(None, db_request)

        assert service.db is db_request.db

    def test_create_api_key(self, api_key_service):
        user = UserFactory.create()
        expires = _in_days(30)

        raw_key, api_key = api_key_service.create_api_key(
            user, "ci", [ApiKeyScope.TestEcho], expires
        )

        assert services.is_well_formed(raw_key)
        assert api_key.id is not None
        assert api_key.user == user
        assert api_key.created_by_id == user.id
        assert api_key.name == "ci"
        assert api_key.hashed_key == services.hash_api_key(raw_key)
        assert api_key.last_four == raw_key[-4:]
        assert api_key.scopes == ["test:echo"]
        assert api_key.expires == expires
        assert api_key.revoked is None
        assert api_key.last_used is None

    def test_create_api_key_deduplicates_scopes(self, api_key_service):
        scope = ApiKeyScope.TestEcho

        _, api_key = api_key_service.create_api_key(
            UserFactory.create(), "ci", [scope, scope], _in_days(30)
        )

        assert api_key.scopes == ["test:echo"]

    def test_create_api_key_at_limit(self, api_key_service):
        user = UserFactory.create()
        ApiKeyFactory.create_batch(services.MAX_ACTIVE_API_KEYS, user=user)

        with pytest.raises(ApiKeyLimitError):
            api_key_service.create_api_key(
                user, "one more", [ApiKeyScope.TestEcho], _in_days(30)
            )

    @pytest.mark.parametrize(
        ("existing", "name"), [("ci", "ci"), ("ci", "CI"), ("Straße", "STRASSE")]
    )
    def test_create_api_key_name_in_use(self, api_key_service, existing, name):
        """Names compare casefolded, the same way for every script."""
        user = UserFactory.create()
        ApiKeyFactory.create(user=user, name=existing)

        with pytest.raises(ApiKeyNameInUseError):
            api_key_service.create_api_key(
                user, name, [ApiKeyScope.TestEcho], _in_days(30)
            )

    @pytest.mark.parametrize(
        "old_key",
        [
            pytest.param({"revoked": now()}, id="revoked"),
            pytest.param(
                {"created": _in_days(-2), "expires": _in_days(-1)}, id="expired"
            ),
        ],
    )
    def test_create_api_key_reuses_inactive_name(self, api_key_service, old_key):
        user = UserFactory.create()
        ApiKeyFactory.create(user=user, name="ci", **old_key)

        _, api_key = api_key_service.create_api_key(
            user, "ci", [ApiKeyScope.TestEcho], _in_days(30)
        )

        assert api_key.name == "ci"

    def test_create_api_key_limit_ignores_inactive(self, api_key_service):
        """Revoked and expired keys don't count toward the limit."""
        user = UserFactory.create()
        ApiKeyFactory.create_batch(
            services.MAX_ACTIVE_API_KEYS - 1, user=user, revoked=now()
        )
        ApiKeyFactory.create(
            user=user,
            created=now() - dt.timedelta(days=2),
            expires=now() - dt.timedelta(days=1),
        )
        ApiKeyFactory.create_batch(services.MAX_ACTIVE_API_KEYS - 1, user=user)

        _, api_key = api_key_service.create_api_key(
            user, "last", [ApiKeyScope.TestEcho], _in_days(30)
        )

        assert api_key.name == "last"

    def test_create_api_key_allows_max_lifetime(self, api_key_service):
        """A 365-day expiry computed after the transaction began still passes."""
        user = UserFactory.create()

        _, api_key = api_key_service.create_api_key(
            user, "max", [ApiKeyScope.TestEcho], _in_days(365)
        )

        assert api_key.id is not None

    def test_create_api_key_rejects_long_expiry(self, api_key_service, db_session):
        """The CHECK constraint caps a key's lifetime."""
        user = UserFactory.create()

        with pytest.raises(
            psycopg.errors.CheckViolation, match="api_keys_max_lifetime"
        ):
            api_key_service.create_api_key(
                user, "too long", [ApiKeyScope.TestEcho], _in_days(367)
            )

    def test_verify(self, api_key_service):
        user = UserFactory.create()
        raw_key, api_key = api_key_service.create_api_key(
            user, "ci", [ApiKeyScope.TestEcho], _in_days(30)
        )

        assert api_key_service.verify(raw_key) == api_key

    def test_record_use(self, api_key_service, db_session):
        api_key = ApiKeyFactory.create()

        api_key_service.record_use(api_key.id)
        db_session.refresh(api_key)

        assert api_key.last_used is not None

    def test_verify_malformed(self, api_key_service, mocker):
        execute = mocker.spy(api_key_service.db, "execute")

        with pytest.raises(InvalidApiKeyError, match="malformed"):
            api_key_service.verify("pypi_mapi_v1_nope")

        execute.assert_not_called()

    def test_verify_unknown(self, api_key_service):
        with pytest.raises(InvalidApiKeyError, match="unknown or revoked"):
            api_key_service.verify(services.generate_api_key())

    def test_verify_revoked(self, api_key_service):
        user = UserFactory.create()
        raw_key, api_key = api_key_service.create_api_key(
            user, "ci", [ApiKeyScope.TestEcho], _in_days(30)
        )
        api_key_service.revoke(api_key.id)

        with pytest.raises(InvalidApiKeyError, match="unknown or revoked"):
            api_key_service.verify(raw_key)

    def test_find(self, api_key_service):
        raw_key = services.generate_api_key()
        api_key = ApiKeyFactory.create(raw_key=raw_key, revoked=now())

        assert api_key_service.find(raw_key) == api_key
        assert api_key_service.find(services.generate_api_key()) is None
        assert api_key_service.find("pypi_mapi_v1_typo") is None

    def test_verify_expired(self, api_key_service):
        raw_key = services.generate_api_key()
        ApiKeyFactory.create(raw_key=raw_key, expires=dt.datetime(2026, 1, 1))

        with pytest.raises(
            InvalidApiKeyError,
            match="Maintainer API key expired at 2026-01-01T00:00:00Z",
        ):
            api_key_service.verify(raw_key)

    def test_revoke(self, api_key_service, db_session):
        api_key = ApiKeyFactory.create()

        assert api_key_service.revoke(api_key.id)
        db_session.refresh(api_key)

        assert api_key.revoked is not None

    def test_revoke_keeps_first_revocation(self, api_key_service, db_session):
        revoked = _in_days(-1)
        api_key = ApiKeyFactory.create(revoked=revoked)

        assert not api_key_service.revoke(api_key.id)
        db_session.refresh(api_key)

        assert api_key.revoked == revoked

    def test_user_delete_cascades(self, db_session):
        api_key = ApiKeyFactory.create()
        user = api_key.user

        db_session.delete(user)
        db_session.flush()

        assert db_session.scalar(select(ApiKey).where(ApiKey.id == api_key.id)) is None
