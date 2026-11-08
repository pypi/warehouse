# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import enum


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
