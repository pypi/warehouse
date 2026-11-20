# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime as dt
import hashlib
import re
import secrets
import string
import zlib

from typing import TYPE_CHECKING, Final

from sqlalchemy import select, update
from zope.interface import implementer

from warehouse.api.maintainer._errors import (
    ApiKeyLimitError,
    ApiKeyNameInUseError,
    InvalidApiKeyError,
)
from warehouse.api.maintainer._interfaces import IApiKeyService
from warehouse.api.maintainer._models import ApiKey
from warehouse.api.maintainer._scopes import ApiKeyScope
from warehouse.utils import now

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from pyramid.request import Request
    from sqlalchemy.orm import Session

    from warehouse.accounts.models import User

API_KEY_PREFIX: Final = "pypi_mapi_v1_"

# Unrevoked, unexpired keys a user may hold at once. Bounds what a stolen
# session can mint, and how many live credentials one account exposes.
MAX_ACTIVE_API_KEYS: Final = 10

_BASE62: Final = string.digits + string.ascii_uppercase + string.ascii_lowercase
_RANDOM_LENGTH: Final = 30
_CHECKSUM_LENGTH: Final = 6
API_KEY_RE: Final = re.compile(
    rf"{API_KEY_PREFIX}[0-9A-Za-z]{{{_RANDOM_LENGTH + _CHECKSUM_LENGTH}}}"
)


def _base62(value: int) -> str:
    """Encode ``value`` in base62, zero-padded to the checksum length."""
    digits: list[str] = []
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
    if not API_KEY_RE.fullmatch(raw_key):
        return False
    body, checksum = raw_key[:-_CHECKSUM_LENGTH], raw_key[-_CHECKSUM_LENGTH:]
    return _checksum(body) == checksum


def hash_api_key(raw_key: str) -> str:
    """The SHA-256 hex digest stored for ``raw_key``."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


@implementer(IApiKeyService)
class DatabaseApiKeyService:
    def __init__(self, db_session: Session) -> None:
        self.db = db_session

    def create_api_key(
        self,
        user: User,
        name: str,
        scopes: Sequence[ApiKeyScope],
        expires: dt.datetime,
    ) -> tuple[str, ApiKey]:
        # Lock the user's row so concurrent creates count one at a time.
        # type(user) is User, imported only for typing to avoid a cycle.
        user_model = type(user)
        self.db.execute(
            select(user_model.id).where(user_model.id == user.id).with_for_update()
        )
        active_names = self.db.scalars(
            select(ApiKey.name).where(
                ApiKey.user_id == user.id,
                ApiKey.revoked.is_(None),
                ApiKey.expires > now(),
            )
        ).all()
        if len(active_names) >= MAX_ACTIVE_API_KEYS:
            raise ApiKeyLimitError
        # Keys are told apart by name in the list and the security history.
        if name.casefold() in {active.casefold() for active in active_names}:
            raise ApiKeyNameInUseError

        raw_key = generate_api_key()
        api_key = ApiKey(
            user=user,
            created_by_id=user.id,
            name=name,
            hashed_key=hash_api_key(raw_key),
            last_four=raw_key[-4:],
            # Deduplicated, in ApiKeyScope order.
            scopes=[str(scope) for scope in ApiKeyScope if scope in scopes],
            expires=expires,
        )
        self.db.add(api_key)
        self.db.flush()  # ast-grep-ignore: db-flush -- generate api_key.id
        return raw_key, api_key

    def find(self, raw_key: str) -> ApiKey | None:
        # A malformed key's hash matches no row.
        return self.db.scalar(
            select(ApiKey).where(ApiKey.hashed_key == hash_api_key(raw_key))
        )

    def verify(self, raw_key: str) -> ApiKey:
        if not is_well_formed(raw_key):
            raise InvalidApiKeyError("malformed Maintainer API key")

        api_key = self.find(raw_key)
        if api_key is None or api_key.revoked is not None:
            raise InvalidApiKeyError("unknown or revoked Maintainer API key")
        if api_key.expires <= now():
            raise InvalidApiKeyError(
                # expires is naive UTC; say so.
                f"Maintainer API key expired at {api_key.expires.isoformat()}Z"
            )
        return api_key

    def record_use(self, api_key_id: UUID) -> None:
        # Like Macaroon.last_used's in-request update: no dirtying the ORM object,
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
            .values(last_used=now())
        )

    def revoke(self, api_key_id: UUID) -> bool:
        revoked_id = self.db.scalar(
            update(ApiKey)
            .where(ApiKey.id == api_key_id, ApiKey.revoked.is_(None))
            .values(revoked=now())
            .returning(ApiKey.id)
        )
        return revoked_id is not None


def database_api_key_factory(
    context: object, request: Request
) -> DatabaseApiKeyService:
    return DatabaseApiKeyService(request.db)
