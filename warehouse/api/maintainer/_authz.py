# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Self

from pyramid.authorization import ACLHelper

from warehouse.api.maintainer._scopes import SCOPE_PERMISSIONS
from warehouse.config import RootFactory
from warehouse.errors import WarehouseDenied
from warehouse.utils.security_policy import principals_for

if TYPE_CHECKING:
    from pyramid.request import Request

    from warehouse.api.maintainer._context import ApiKeyContext
    from warehouse.api.maintainer._scopes import ApiKeyScope

ACL: Final = ACLHelper()


def owner_holds_scope(
    request: Request, identity: ApiKeyContext, scope: ApiKeyScope
) -> bool:
    """Whether the key's owner holds ``scope``'s permission on the site root."""
    return bool(
        ACL.permits(
            RootFactory(request), principals_for(identity), SCOPE_PERMISSIONS[scope]
        )
    )


class InsufficientScope(WarehouseDenied):
    """A denial because the key's scope doesn't cover the request."""

    scope: ApiKeyScope

    def __new__(cls, s: str, *, scope: ApiKeyScope) -> Self:
        inner = super().__new__(cls, s, reason="insufficient_scope")
        inner.scope = scope
        return inner
