# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warehouse.accounts.models import User
    from warehouse.api.maintainer._models import ApiKey


@dataclass
class ApiKeyContext:
    """The identity for a request authenticated with a Maintainer API key."""

    user: User
    api_key: ApiKey
    # Set once permits() records the key's use, so a request records it once.
    use_recorded: bool = field(default=False, compare=False)

    def __principals__(self) -> list[str]:
        return self.user.__principals__()
