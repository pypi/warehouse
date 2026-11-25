# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import TYPE_CHECKING

from zope.interface import Interface

if TYPE_CHECKING:
    import datetime as dt

    from collections.abc import Sequence
    from uuid import UUID

    from warehouse.accounts.models import User
    from warehouse.api.maintainer._models import ApiKey
    from warehouse.api.maintainer._scopes import ApiKeyScope


class IApiKeyService(Interface):
    def create_api_key(
        user: User, name: str, scopes: Sequence[ApiKeyScope], expires: dt.datetime
    ) -> tuple[str, ApiKey]:
        """
        Returns a tuple of the new raw key and its DB model. The raw key is
        not stored and cannot be recovered later.

        Raises ApiKeyLimitError if the user already holds the most active
        keys allowed, and ApiKeyNameInUseError if one of their active keys
        has this name, ignoring case.

        Does not check whether the user may hold the scopes. Callers offer
        only the scopes in SCOPE_PERMISSIONS that the user holds, and the
        security policy checks again on every request.
        """

    def find(raw_key: str) -> ApiKey | None:
        """
        Returns the DB model for the key, revoked or expired included, or None
        if it is unknown.
        """

    def verify(raw_key: str) -> ApiKey:
        """
        Returns the DB model for an active key.

        Raises InvalidApiKeyError if the key is malformed, unknown, revoked or
        expired. Its message says whether the key is malformed, unknown or
        revoked, or expired, for the key's holder.
        """

    def record_use(api_key_id: UUID) -> None:
        """
        Marks the key with the given ID as used now.
        """

    def revoke(api_key_id: UUID) -> bool:
        """
        Revokes the key with the given ID, effective immediately. Returns
        whether this call revoked it, False if it was already revoked.
        """
