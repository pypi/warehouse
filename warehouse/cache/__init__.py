# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing

from .interfaces import IQueryResultsCache
from .services import RedisQueryResults

if typing.TYPE_CHECKING:
    from pyramid.config import Configurator


def includeme(config: Configurator) -> None:
    config.register_service_factory(
        RedisQueryResults.create_service, IQueryResultsCache
    )
