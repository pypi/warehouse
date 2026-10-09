# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warehouse.accounts.models import User
    from warehouse.api.maintainer._models import ApiKey


@dataclass
class ApiKeyContext:
    """
    The identity for a request authenticated with a Maintainer API key.
    Supports `ApiKeySecurityPolicy` in `warehouse.api.maintainer._security_policy`.
    """

    user: User
    api_key: ApiKey

    def __principals__(self) -> list[str]:
        return self.user.__principals__()
