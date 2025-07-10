# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse.cache import includeme
from warehouse.cache.interfaces import IQueryResultsCache
from warehouse.cache.services import RedisQueryResults


def test_includeme():
    config = pretend.stub(
        register_service_factory=pretend.call_recorder(lambda *a, **k: None)
    )

    includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(RedisQueryResults.create_service, IQueryResultsCache)
    ]
