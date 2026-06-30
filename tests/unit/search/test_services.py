# SPDX-License-Identifier: Apache-2.0

from warehouse.search.services import NullSearchService


class TestSearchService:
    def test_null_service(self, mocker):
        service = NullSearchService.create_service(
            mocker.sentinel.context, mocker.sentinel.request
        )
        config = mocker.sentinel.config

        assert service.reindex(config, ["foo", "bar"]) is None
        assert service.unindex(config, ["foo", "bar"]) is None
