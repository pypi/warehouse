# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime
import hashlib
import re
import secrets
import string
import zlib

from typing import TYPE_CHECKING

from sqlalchemy import select, update
from zope.interface import implementer

from warehouse.api.maintainer._errors import ExpiredApiKeyError, InvalidApiKeyError
from warehouse.api.maintainer._interfaces import IApiKeyService
from warehouse.api.maintainer._models import ApiKey, ApiKeyScope

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

API_KEY_PREFIX = "pypi_mapi_v1_"

_BASE62 = string.digits + string.ascii_uppercase + string.ascii_lowercase
_RANDOM_LENGTH = 30
_CHECKSUM_LENGTH = 6
_API_KEY_RE = re.compile(
    rf"{API_KEY_PREFIX}[0-9A-Za-z]{{{_RANDOM_LENGTH + _CHECKSUM_LENGTH}}}"
)


def _base62(value: int) -> str:
    """Encode ``value`` in base62, zero-padded to the checksum length."""
    digits = []
    while value:
        value, remainder = divmod(value, 62)
        digits.append(_BASE62[remainder])
    return "".join(reversed(digits)).rjust(_CHECKSUM_LENGTH, _BASE62[0])


def _checksum(body: str) -> str:
    """CRC32 of ``body``, base62-encoded. Detects typos, proves nothing."""
    return _base62(zlib.crc32(body.encode()))


def generate_api_key() -> str:
    """Return a new ``pypi_mapi_v1_<random><checksum>`` key."""
    body = API_KEY_PREFIX + "".join(
        secrets.choice(_BASE62) for _ in range(_RANDOM_LENGTH)
    )
    return body + _checksum(body)


def is_well_formed(raw_key: str) -> bool:
    """Whether ``raw_key`` has the right shape and a matching checksum."""
    if not _API_KEY_RE.fullmatch(raw_key):
        return False
    body, checksum = raw_key[:-_CHECKSUM_LENGTH], raw_key[-_CHECKSUM_LENGTH:]
    return secrets.compare_digest(_checksum(body), checksum)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


@implementer(IApiKeyService)
class DatabaseApiKeyService:
    def __init__(self, db_session: Session):
        self.db = db_session

    def create_api_key(
        self,
        user_id: UUID,
        name: str,
        scopes: list[ApiKeyScope],
        expires: datetime.datetime,
    ) -> tuple[str, ApiKey]:
        raw_key = generate_api_key()
        api_key = ApiKey(
            user_id=user_id,
            created_by_id=user_id,
            name=name,
            hashed_key=hash_api_key(raw_key),
            last_four=raw_key[-4:],
            scopes=[str(scope) for scope in scopes],
            expires=expires,
        )
        self.db.add(api_key)
        self.db.flush()  # ast-grep-ignore: db-flush -- generate api_key.id
        return raw_key, api_key

    def verify(self, raw_key: str) -> ApiKey:
        if not is_well_formed(raw_key):
            raise InvalidApiKeyError("malformed API key")

        api_key = self.db.scalar(
            select(ApiKey).where(ApiKey.hashed_key == hash_api_key(raw_key))
        )
        if api_key is None or api_key.revoked is not None:
            raise InvalidApiKeyError("unknown or revoked API key")

        if api_key.expires <= _now():
            raise ExpiredApiKeyError(api_key.expires)

        return api_key

    def record_use(self, api_key_id: UUID) -> None:
        # Same as Macaroon.last_used: update without dirtying the ORM object,
        # and skip if a concurrent request already holds the row.
        self.db.execute(
            update(ApiKey)
            .where(
                ApiKey.id.in_(
                    select(ApiKey.id)
                    .where(ApiKey.id == api_key_id)
                    .with_for_update(skip_locked=True)
                )
            )
            .values(last_used=_now())
        )

    def revoke(self, api_key_id: UUID) -> None:
        self.db.execute(
            update(ApiKey)
            .where(ApiKey.id == api_key_id, ApiKey.revoked.is_(None))
            .values(revoked=_now())
        )


def database_api_key_factory(context, request) -> DatabaseApiKeyService:
    return DatabaseApiKeyService(request.db)
