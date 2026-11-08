# SPDX-License-Identifier: Apache-2.0
"""
Maintainer API keys: long-lived bearer credentials for the Maintainer API.

Import from this package. Its private submodules, named with a leading
underscore, can be reorganized freely; ``pyproject.toml`` bans importing them
from outside.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from warehouse.api.maintainer._errors import (
    ApiKeyLimitError,
    ApiKeyNameInUseError,
    InvalidApiKeyError,
)
from warehouse.api.maintainer._interfaces import IApiKeyService
from warehouse.api.maintainer._models import ApiKey
from warehouse.api.maintainer._scopes import ApiKeyScope
from warehouse.api.maintainer._services import (
    API_KEY_PREFIX,
    API_KEY_RE,
    MAX_ACTIVE_API_KEYS,
    DatabaseApiKeyService,
    database_api_key_factory,
    generate_api_key,
    hash_api_key,
)

if TYPE_CHECKING:
    from pyramid.config import Configurator

__all__ = [
    "API_KEY_PREFIX",
    "API_KEY_RE",
    "MAX_ACTIVE_API_KEYS",
    "ApiKey",
    "ApiKeyLimitError",
    "ApiKeyNameInUseError",
    "ApiKeyScope",
    "DatabaseApiKeyService",
    "IApiKeyService",
    "InvalidApiKeyError",
    "generate_api_key",
    "hash_api_key",
    "includeme",
]


def includeme(config: Configurator) -> None:
    config.register_service_factory(database_api_key_factory, IApiKeyService)
