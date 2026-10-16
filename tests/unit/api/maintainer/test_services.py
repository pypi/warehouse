# SPDX-License-Identifier: Apache-2.0

import datetime
import hashlib
import zlib

import psycopg
import pytest

from sqlalchemy import select
from zope.interface.verify import verifyClass

from warehouse.api.maintainer import (
    ApiKey,
    ApiKeyScope,
    ExpiredApiKeyError,
    IApiKeyService,
    InvalidApiKeyError,
    _services as services,
)

from ....common.db.accounts import UserFactory
from ....common.db.maintainer_api import ApiKeyFactory


def _in_days(days):
    return datetime.datetime.now() + datetime.timedelta(days=days)


def test_generate_api_key_format():
    raw_key = services.generate_api_key()

    assert raw_key.startswith("pypi_mapi_v1_")
    assert len(raw_key) == 13 + 30 + 6
    assert services.is_well_formed(raw_key)


def test_generate_api_key_is_random():
    assert services.generate_api_key() != services.generate_api_key()


def test_checksum_is_base62_crc32():
    """The trailer is CRC32 of the prefix and random segment, zero-padded."""
    raw_key = services.generate_api_key()
    body, checksum = raw_key[:-6], raw_key[-6:]

    decoded = 0
    for char in checksum:
        decoded = decoded * 62 + services._BASE62.index(char)

    assert decoded == zlib.crc32(body.encode())


def test_base62_pads_small_values():
    assert services._base62(0) == "000000"
    assert services._base62(61) == "00000z"


@pytest.mark.parametrize(
    "raw_key",
    [
        pytest.param("", id="empty"),
        pytest.param("pypi-AgEIcHlwaS5vcmc", id="upload token"),
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
            user.id, "ci", [ApiKeyScope.ProjectReleasesYank], expires
        )

        assert services.is_well_formed(raw_key)
        assert api_key.id is not None
        assert api_key.user == user
        assert api_key.created_by_id == user.id
        assert api_key.name == "ci"
        assert api_key.hashed_key == services.hash_api_key(raw_key)
        assert api_key.last_four == raw_key[-4:]
        assert api_key.scopes == ["project:releases:yank"]
        assert api_key.expires == expires
        assert api_key.revoked is None
        assert api_key.last_used is None

    def test_create_api_key_allows_max_lifetime(self, api_key_service):
        """A 365-day expiry computed after the transaction began still passes."""
        user = UserFactory.create()

        _, api_key = api_key_service.create_api_key(
            user.id, "max", [ApiKeyScope.ProjectReleasesYank], _in_days(365)
        )

        assert api_key.id is not None

    def test_create_api_key_rejects_long_expiry(self, api_key_service, db_session):
        """The CHECK constraint caps a key's lifetime."""
        user = UserFactory.create()

        with pytest.raises(
            psycopg.errors.CheckViolation, match="api_keys_max_lifetime"
        ):
            api_key_service.create_api_key(
                user.id, "too long", [ApiKeyScope.ProjectReleasesYank], _in_days(367)
            )

    def test_verify(self, api_key_service, db_session):
        user = UserFactory.create()
        raw_key, api_key = api_key_service.create_api_key(
            user.id, "ci", [ApiKeyScope.ProjectReleasesYank], _in_days(30)
        )

        assert api_key_service.verify(raw_key) == api_key

        db_session.refresh(api_key)
        assert api_key.last_used is None

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
            user.id, "ci", [ApiKeyScope.ProjectReleasesYank], _in_days(30)
        )
        api_key_service.revoke(api_key.id)

        with pytest.raises(InvalidApiKeyError, match="unknown or revoked"):
            api_key_service.verify(raw_key)

    def test_verify_expired(self, api_key_service):
        raw_key = services.generate_api_key()
        expired = _in_days(-1)
        ApiKeyFactory.create(hashed_key=services.hash_api_key(raw_key), expires=expired)

        with pytest.raises(ExpiredApiKeyError) as excinfo:
            api_key_service.verify(raw_key)

        assert excinfo.value.expired == expired

    def test_revoke(self, api_key_service, db_session):
        api_key = ApiKeyFactory.create()

        api_key_service.revoke(api_key.id)
        db_session.refresh(api_key)

        assert api_key.revoked is not None

    def test_revoke_keeps_first_revocation(self, api_key_service, db_session):
        revoked = _in_days(-1)
        api_key = ApiKeyFactory.create(revoked=revoked)

        api_key_service.revoke(api_key.id)
        db_session.refresh(api_key)

        assert api_key.revoked == revoked

    def test_user_delete_cascades(self, db_session):
        api_key = ApiKeyFactory.create()
        user = api_key.user

        db_session.delete(user)
        db_session.flush()

        assert db_session.scalar(select(ApiKey).where(ApiKey.id == api_key.id)) is None
