# SPDX-License-Identifier: Apache-2.0

from warehouse.cache import includeme
from warehouse.cache.interfaces import IQueryResultsCache
from warehouse.cache.services import RedisQueryResults


def test_includeme(mocker):
    config = mocker.Mock(spec=["register_service_factory"])

    includeme(config)

    config.register_service_factory.assert_called_once_with(
        RedisQueryResults.create_service, IQueryResultsCache
    )
