# Copyright 2013 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function
from __future__ import unicode_literals

import os

import pretend
import pytest

from elasticsearch import TransportError

from warehouse.search import indexes
from warehouse.search.indexes import Index, BaseMapping


class TestIndex:

    def test_reindex(self, monkeypatch):
        urandom = pretend.call_recorder(lambda s: b"0" * s)
        monkeypatch.setattr(os, "urandom", urandom)

        models = pretend.stub()
        config = pretend.stub(hosts=[])

        index = Index(models, config)
        index.es = pretend.stub(
            indices=pretend.stub(
                create=pretend.call_recorder(lambda idx, body: None),
            ),
        )
        index.types = {
            "fake": pretend.stub(
                _type="fake",
                get_mapping=pretend.call_recorder(lambda: {"foo": "bar"}),
                index_all=pretend.call_recorder(lambda index: None),
            ),
        }
        index.update_alias = pretend.call_recorder(lambda *a, **kw: None)

        index.reindex()

        assert index.es.indices.create.calls == [
            pretend.call(
                "warehouse1e4a1b03",
                {"mappings": {"fake": {"foo": "bar"}}},
            ),
        ]
        assert index.update_alias.calls == [
            pretend.call("warehouse", "warehouse1e4a1b03", keep_old=False),
        ]
        assert index.types["fake"].index_all.calls == [
            pretend.call(index="warehouse1e4a1b03"),
        ]

    def test_reindex_no_alias(self, monkeypatch):
        urandom = pretend.call_recorder(lambda s: b"0" * s)
        monkeypatch.setattr(os, "urandom", urandom)

        models = pretend.stub()
        config = pretend.stub(hosts=[])

        index = Index(models, config)
        index.es = pretend.stub(
            indices=pretend.stub(
                create=pretend.call_recorder(lambda idx, body: None),
            ),
        )
        index.types = {
            "fake": pretend.stub(
                _type="fake",
                get_mapping=pretend.call_recorder(lambda: {"foo": "bar"}),
                index_all=pretend.call_recorder(lambda index: None),
            ),
        }
        index.update_alias = pretend.call_recorder(lambda *a, **kw: None)

        index.reindex(alias=False)

        assert index.es.indices.create.calls == [
            pretend.call(
                "warehouse1e4a1b03",
                {"mappings": {"fake": {"foo": "bar"}}},
            ),
        ]
        assert index.update_alias.calls == []
        assert index.types["fake"].index_all.calls == [
            pretend.call(index="warehouse1e4a1b03"),
        ]

    def test_update_alias(self):
        models = pretend.stub()
        config = pretend.stub(hosts=[])

        index = Index(models, config)
        index.es = pretend.stub(
            indices=pretend.stub(
                get_alias=pretend.call_recorder(
                    lambda idx: {"warehouse1234567": "warehouse"},
                ),
                update_aliases=pretend.call_recorder(lambda actions: None),
                delete=pretend.call_recorder(lambda idx: None)
            ),
        )

        index.update_alias("warehouse", "warehouse7654321")

        assert index.es.indices.get_alias.calls == [pretend.call("warehouse")]
        assert index.es.indices.update_aliases.calls == [
            pretend.call({"actions": [
                {
                    "remove": {
                        "index": "warehouse1234567",
                        "alias": "warehouse",
                    },
                },
                {"add": {"index": "warehouse7654321", "alias": "warehouse"}}
            ]}),
        ]
        assert index.es.indices.delete.calls == [
            pretend.call("warehouse1234567"),
        ]

    def test_update_alias_no_old_index(self):
        models = pretend.stub()
        config = pretend.stub(hosts=[])

        def _get_alias(idx):
            raise TransportError(404, "Fake 404")

        index = Index(models, config)
        index.es = pretend.stub(
            indices=pretend.stub(
                get_alias=pretend.call_recorder(_get_alias),
                update_aliases=pretend.call_recorder(lambda actions: None),
                delete=pretend.call_recorder(lambda idx: None)
            ),
        )

        index.update_alias("warehouse", "warehouse7654321")

        assert index.es.indices.get_alias.calls == [pretend.call("warehouse")]
        assert index.es.indices.update_aliases.calls == [
            pretend.call({"actions": [
                {"add": {"index": "warehouse7654321", "alias": "warehouse"}}
            ]}),
        ]
        assert index.es.indices.delete.calls == []

    def test_update_alias_exception(self):
        models = pretend.stub()
        config = pretend.stub(hosts=[])

        def _get_alias(idx):
            raise TransportError(500, "Fake 500")

        index = Index(models, config)
        index.es = pretend.stub(
            indices=pretend.stub(
                get_alias=pretend.call_recorder(_get_alias),
            ),
        )

        with pytest.raises(TransportError):
            index.update_alias("warehouse", "warehouse7654321")

        assert index.es.indices.get_alias.calls == [pretend.call("warehouse")]


class TestBaseMapping:

    def test_get_mapping(self):
        bmap = BaseMapping(index=pretend.stub())

        with pytest.raises(NotImplementedError):
            bmap.get_mapping()

    def test_get_indexable(self):
        bmap = BaseMapping(index=pretend.stub())

        with pytest.raises(NotImplementedError):
            bmap.get_indexable()

    def test_extract_id(self):
        bmap = BaseMapping(index=pretend.stub())

        with pytest.raises(NotImplementedError):
            bmap.extract_id(None)

    def test_extract_document(self):
        bmap = BaseMapping(index=pretend.stub())

        with pytest.raises(NotImplementedError):
            bmap.extract_document(None)

    def test_search(self):
        bmap = BaseMapping(index=pretend.stub())

        with pytest.raises(NotImplementedError):
            bmap.search(None)

    def test_index_all(self, monkeypatch):
        bulk_index = pretend.call_recorder(lambda es, docs: None)
        monkeypatch.setattr(indexes, "bulk_index", bulk_index)

        index = pretend.stub(
            _index="warehouse",
            es=pretend.stub(),
        )

        bmap = BaseMapping(index=index)
        bmap.get_indexable = pretend.call_recorder(lambda: [])
        bmap.index_all()

        assert bulk_index.calls == [pretend.call(index.es, [])]
        assert bmap.get_indexable.calls == [pretend.call()]
