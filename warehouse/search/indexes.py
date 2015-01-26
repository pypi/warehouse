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

import binascii
import os

from elasticsearch import Elasticsearch, TransportError
from elasticsearch.helpers import bulk_index

from warehouse.datastructures import AttributeDict


class Index(object):

    def __init__(self, db, config):
        self.db = db
        self.config = config
        self.es = Elasticsearch(
            hosts=self.config.hosts or ['127.0.0.1:9200'],
            **self.config.get("client_options", {})
        )

        self.types = AttributeDict()

        self._index = config.index

    def register(self, type_):
        obj = type_(self)
        self.types[obj._type] = obj

    def reindex(self, alias=True, keep_old=False):
        # Generate an Index Name for Warehouse
        index = "".join([
            self._index,
            binascii.hexlify(os.urandom(4)).decode("ascii"),
        ])

        # Create this index
        self.es.indices.create(index, {
            "mappings": {
                doc_type._type: doc_type.get_mapping()
                for doc_type in self.types.values()
            },
        })

        # Index everything into the new index
        for doc_type in self.types.values():
            doc_type.index_all(index=index)

        # Update the alias unless we've been told not to
        if alias:
            self.update_alias(self._index, index, keep_old=keep_old)

    def update_alias(self, alias, index, keep_old=False):
        # Get the old index from ElasticSearch
        try:
            old_index = list(self.es.indices.get_alias(self._index))[0]
        except TransportError as exc:
            if not exc.status_code == 404:
                raise
            old_index = None

        # Remove the alias to the old index if it exists
        if old_index is not None:
            actions = [{"remove": {"index": old_index, "alias": alias}}]
        else:
            actions = []

        # Add the alias to the new index
        actions += [{"add": {"index": index, "alias": alias}}]

        # Update To the New Index
        self.es.indices.update_aliases({"actions": actions})

        # Delete the old index if it exists and unless we're keeping it
        if not keep_old and old_index is not None:
            self.es.indices.delete(old_index)


class BaseMapping(object):

    SEARCH_LIMIT = 25

    def __init__(self, index):
        self.index = index

    def get_mapping(self):
        raise NotImplementedError

    def get_indexable(self):
        raise NotImplementedError

    def extract_id(self, item):
        raise NotImplementedError

    def extract_document(self, item):
        raise NotImplementedError

    def index_all(self, index=None):
        # Determine which index we are indexing into
        _index = index if index is not None else self.index._index

        # Bulk Index our documents
        bulk_index(
            self.index.es,
            [
                {
                    "_index": _index,
                    "_type": self._type,
                    "_id": self.extract_id(item),
                    "_source": self.extract_document(item),
                }
                for item in self.get_indexable()
            ],
        )

    def search(self, query):
        raise NotImplementedError
