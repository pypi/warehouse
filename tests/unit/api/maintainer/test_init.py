# SPDX-License-Identifier: Apache-2.0

from warehouse.api import maintainer
from warehouse.api.maintainer import IApiKeyService
from warehouse.api.maintainer._services import database_api_key_factory


def test_includeme(mocker):
    config = mocker.Mock()

    maintainer.includeme(config)

    config.register_service_factory.assert_called_once_with(
        database_api_key_factory, IApiKeyService
    )
