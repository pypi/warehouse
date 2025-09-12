# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse.search.services import NullSearchService


class TestSearchService:
    def test_null_service(self):
        service = NullSearchService.create_service(pretend.stub(), pretend.stub())
        config = pretend.stub()

        assert service.reindex(config, ["foo", "bar"]) is None
        assert service.unindex(config, ["foo", "bar"]) is None
