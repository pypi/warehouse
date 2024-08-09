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


import pytest

from opensearchpy import Search

from warehouse.search import queries

EXPECTED_SEARCH_FIELDS = [
    "author",
    "author_email",
    "description^5",
    "download_url",
    "home_page",
    "keywords^5",
    "license",
    "maintainer",
    "maintainer_email",
    "normalized_name^10",
    "platform",
    "summary^5",
]


class TestQueries:
    def test_no_terms(self):
        opensearch = Search()

        query = queries.get_opensearch_query(opensearch, "", "", [])

        assert query.to_dict() == {"query": {"match_all": {}}}

    @pytest.mark.parametrize(
        "terms,expected_prefix,expected_type",
        [
            ('"foo bar"', '"foo bar"', "phrase"),
            ('"a"', '"a"', "phrase"),
            ("foo bar", "foo bar", "best_fields"),
        ],
    )
    def test_quoted_query(self, terms, expected_prefix, expected_type):
        opensearch = Search()

        query = queries.get_opensearch_query(opensearch, terms, "", [])

        assert query.to_dict() == {
            "query": {
                "bool": {
                    "should": [
                        {
                            "bool": {
                                "must": [
                                    {
                                        "multi_match": {
                                            "fields": EXPECTED_SEARCH_FIELDS,
                                            "query": (
                                                "foo bar" if terms != '"a"' else "a"
                                            ),
                                            "type": expected_type,
                                        }
                                    },
                                ]
                            }
                        },
                        {"prefix": {"normalized_name": expected_prefix}},
                    ]
                }
            },
            "suggest": {"name_suggestion": {"text": terms, "term": {"field": "name"}}},
        }

    def test_single_not_quoted_character(self):
        opensearch = Search()
        terms = "a"

        query = queries.get_opensearch_query(opensearch, terms, "", [])

        assert query.to_dict() == {
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "fields": EXPECTED_SEARCH_FIELDS,
                                "query": "a",
                                "type": "best_fields",
                            }
                        },
                    ]
                }
            },
            "suggest": {"name_suggestion": {"text": "a", "term": {"field": "name"}}},
        }

    def test_mixed_quoted_query(self):
        opensearch = Search()
        terms = '"foo bar" baz'

        query = queries.get_opensearch_query(opensearch, terms, "", [])

        assert query.to_dict() == {
            "query": {
                "bool": {
                    "should": [
                        {
                            "bool": {
                                "must": [
                                    {
                                        "multi_match": {
                                            "fields": EXPECTED_SEARCH_FIELDS,
                                            "query": "foo bar",
                                            "type": "phrase",
                                        }
                                    },
                                    {
                                        "multi_match": {
                                            "fields": EXPECTED_SEARCH_FIELDS,
                                            "query": "baz",
                                            "type": "best_fields",
                                        }
                                    },
                                ]
                            }
                        },
                        {"prefix": {"normalized_name": '"foo bar" baz'}},
                    ]
                }
            },
            "suggest": {
                "name_suggestion": {"text": '"foo bar" baz', "term": {"field": "name"}}
            },
        }

    @pytest.mark.parametrize("order,field", [("created", "created")])
    def test_sort_order(self, order, field):
        opensearch = Search()
        terms = "foo bar"

        query = queries.get_opensearch_query(opensearch, terms, order, [])

        assert query.to_dict() == {
            "query": {
                "bool": {
                    "should": [
                        {
                            "bool": {
                                "must": [
                                    {
                                        "multi_match": {
                                            "fields": EXPECTED_SEARCH_FIELDS,
                                            "query": terms,
                                            "type": "best_fields",
                                        }
                                    },
                                ]
                            }
                        },
                        {"prefix": {"normalized_name": terms}},
                    ]
                }
            },
            "suggest": {"name_suggestion": {"text": terms, "term": {"field": "name"}}},
            "sort": [
                {
                    field: {
                        "order": "desc" if order.startswith("-") else "asc",
                        "unmapped_type": "long",
                    }
                }
            ],
        }

    def test_with_classifiers_with_terms(self):
        opensearch = Search()
        terms = "foo bar"
        classifiers = ["foo :: bar", "fiz :: buz"]

        query = queries.get_opensearch_query(opensearch, terms, "", classifiers)

        assert query.to_dict() == {
            "query": {
                "bool": {
                    "should": [
                        {
                            "bool": {
                                "must": [
                                    {
                                        "multi_match": {
                                            "fields": EXPECTED_SEARCH_FIELDS,
                                            "query": terms,
                                            "type": "best_fields",
                                        }
                                    },
                                    {
                                        "bool": {
                                            "must": [
                                                {
                                                    "bool": {
                                                        "should": [
                                                            {
                                                                "term": {
                                                                    "classifiers": classifier  # noqa
                                                                }
                                                            },
                                                            {
                                                                "prefix": {
                                                                    "classifiers": classifier  # noqa
                                                                    + " :: "
                                                                }
                                                            },
                                                        ]
                                                    }
                                                }
                                                for classifier in classifiers
                                            ]
                                        }
                                    },
                                ]
                            }
                        },
                        {"prefix": {"normalized_name": terms}},
                    ]
                }
            },
            "suggest": {"name_suggestion": {"text": terms, "term": {"field": "name"}}},
        }

    def test_with_classifiers_with_no_terms(self):
        opensearch = Search()
        terms = ""
        classifiers = ["foo :: bar", "fiz :: buz"]

        query = queries.get_opensearch_query(opensearch, terms, "", classifiers)

        assert query.to_dict() == {
            "query": {
                "bool": {
                    "must": [
                        {
                            "bool": {
                                "should": [
                                    {"term": {"classifiers": classifier}},
                                    {"prefix": {"classifiers": classifier + " :: "}},
                                ]
                            }
                        }
                        for classifier in classifiers
                    ]
                }
            }
        }

    def test_with_classifier_with_no_terms_and_order(self):
        opensearch = Search()
        terms = ""
        classifiers = ["foo :: bar"]

        query = queries.get_opensearch_query(opensearch, terms, "-created", classifiers)

        assert query.to_dict() == {
            "query": {
                "bool": {
                    "must": [
                        {
                            "bool": {
                                "should": [
                                    {"term": {"classifiers": "foo :: bar"}},
                                    {"prefix": {"classifiers": "foo :: bar :: "}},
                                ]
                            }
                        }
                    ]
                }
            },
            "sort": [{"created": {"order": "desc", "unmapped_type": "long"}}],
        }
