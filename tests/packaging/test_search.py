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

import pretend
import pytest

from warehouse.packaging.search import ProjectMapping


def test_get_mapping():
    pmap = ProjectMapping(index=pretend.stub())
    assert pmap.get_mapping() == {
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


def test_get_indexable():
    index = pretend.stub(
        db=pretend.stub(
            packaging=pretend.stub(
                get_full_latest_releases=pretend.call_recorder(lambda: []),
            ),
        ),
    )
    pmap = ProjectMapping(index=index)
    pmap.get_indexable()

    assert index.db.packaging.get_full_latest_releases.calls == [
        pretend.call(),
    ]


def test_extract_id():
    pmap = ProjectMapping(index=pretend.stub())
    assert pmap.extract_id({"name": "test name"}) == "test name"


def test_extract_document():
    pmap = ProjectMapping(index=pretend.stub())
    document = pmap.extract_document({"name": "Test Name"})

    assert document == {"name": "Test Name", "name_keyword": "test name"}


@pytest.mark.parametrize(("query", "body"), [
    (None, {"query": {"match_all": {}}, "from": 0, "size": 25}),
    (
        "Django",
        {
            "query": {
                "bool": {
                    "should": [
                        {"term": {"name_keyword": {"value": "django"}}},
                        {
                            "match": {
                                "name": {"query": "django", "boost": 2.0},
                            },
                        },
                        {
                            "match": {
                                "summary": {"query": "django", "boost": 1.5},
                            },
                        },
                        {"match": {"description": {"query": "django"}}},
                    ],
                }
            },
            "from": 0,
            "size": 25,
        },
    ),
])
def test_search(query, body):
    index = pretend.stub(
        _index="warehouse",
        es=pretend.stub(
            search=pretend.call_recorder(lambda **kw: []),
        ),
    )
    pmap = ProjectMapping(index=index)
    pmap.search(query)

    assert index.es.search.calls == [
        pretend.call(index="warehouse", doc_type="project", body=body),
    ]
