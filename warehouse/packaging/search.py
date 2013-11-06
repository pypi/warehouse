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

from warehouse.search.indexes import BaseMapping


class ProjectMapping(BaseMapping):

    _type = "project"

    def get_mapping(self):
        return {
            "properties": {
                "name": {"type": "string"},
                "name_keyword": {"type": "string", "index": "not_analyzed"},
                "version": {"type": "string"},
                "author": {"type": "string"},
                "author_email": {"type": "string"},
                "maintainer": {"type": "string"},
                "maintainer_email": {"type": "string"},
                "home_page": {"type": "string"},
                "license": {"type": "string"},
                "summary": {"type": "string"},
                "description": {"type": "string"},
                "keywords": {"type": "string"},
                "platform": {"type": "string"},
                "download_url": {"type": "string"},
                "created": {"type": "string"},
            },
        }

    def get_indexable(self):
        return self.index.models.packaging.get_full_latest_releases()

    def extract_id(self, item):
        return item["name"]

    def extract_document(self, item):
        item['name_keyword'] = item['name'].lower()
        return item

    def search(self, query, limit=None, offset=0):
        # TODO: Faceting
        # TODO: Other Features?

        limit = limit or self.SEARCH_LIMIT

        if query:
            query = query.lower()
            body = {
                "query": {
                    "bool": {
                        "should": [
                            # An extra boost for exact matches.
                            {
                                "term": {
                                    "name_keyword": {"value": query},
                                }
                            },
                            {
                                "match": {
                                    "name": {"query": query, "boost": 2.0},
                                },
                            },
                            {
                                "match": {
                                    "summary": {"query": query, "boost": 1.5},
                                },
                            },
                            {"match": {"description": {"query": query}}},
                        ],
                    }
                },
                "from": offset,
                "size": limit,
            }
        else:
            body = {
                "query": {"match_all": {}},
                "from": offset,
                "size": limit,
            }

        return self.index.es.search(
            index=self.index._index,
            doc_type=self._type,
            body=body
        )
