# SPDX-License-Identifier: Apache-2.0

from warehouse.api.maintainer._errors import ExpiredApiKeyError, InvalidApiKeyError
from warehouse.api.maintainer._interfaces import IApiKeyService
from warehouse.api.maintainer._models import ApiKey, ApiKeyScope
from warehouse.api.maintainer._services import database_api_key_factory

__all__ = [
    "ApiKey",
    "ApiKeyScope",
    "ExpiredApiKeyError",
    "IApiKeyService",
    "InvalidApiKeyError",
    "includeme",
]


def includeme(config):
    config.register_service_factory(database_api_key_factory, IApiKeyService)
