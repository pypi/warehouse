# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import enum

from typing import TYPE_CHECKING, Final

from warehouse.authnz import Permissions

if TYPE_CHECKING:
    from collections.abc import Mapping


class ApiKeyScope(enum.StrEnum):
    """
    What a Maintainer API key may do, as ``<domain>:<resource>:<action>``.
    A request needs the scope on the key, the owner's ``SCOPE_PERMISSIONS``
    permission for it, and the matching permission on the target resource.

    Scopes under ``test:`` exercise the Maintainer API before real endpoints
    exist.
    """

    TestEcho = "test:echo"
    TestTokenExchange = "test:token:exchange"


# The scope a key must carry for each permission it may exercise. A permission
# that API_KEY may grant but that is missing here is denied. Keyed by str, as
# Pyramid passes permissions; every key is a Permissions member.
PERMISSION_SCOPES: Final[Mapping[str, ApiKeyScope]] = {
    Permissions.APIEcho: ApiKeyScope.TestEcho,
}

# The permission, on the site root, that a user needs to hold each scope. It is
# checked when a key is created and again on every request, so a key stops
# working when its owner loses the permission. Every ApiKeyScope needs an
# entry.
SCOPE_PERMISSIONS: Final[Mapping[ApiKeyScope, Permissions]] = {
    ApiKeyScope.TestEcho: Permissions.APIKeyScopesTest,
    ApiKeyScope.TestTokenExchange: Permissions.APIKeyScopesTest,
}
