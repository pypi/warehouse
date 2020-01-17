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

from elasticsearch_dsl import Search

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
    def test_no_querystring(self):
        es = Search()

        query = queries.get_es_query(es, "", "", [])

        assert query == es.query()

    @pytest.mark.parametrize(
        "querystring,expected_prefix,expected_type",
        [
            ('"foo bar"', '"foo bar"', "phrase"),
            ('"a"', '"a"', "phrase"),
            ("foo bar", "foo bar", "best_fields"),
        ],
    )
    def test_quoted_query(self, querystring, expected_prefix, expected_type):
        es = Search()

        query = queries.get_es_query(es, querystring, "", [])

        query_dict = query.to_dict()
        assert len(query_dict["query"]["bool"]["should"]) == 2
        assert query_dict["query"]["bool"]["should"][1] == {
            "prefix": {"normalized_name": expected_prefix}
        }
        must_params = query_dict["query"]["bool"]["should"][0]["bool"]["must"]
        assert len(must_params) == 1
        assert must_params[0]["multi_match"] == {
            "fields": EXPECTED_SEARCH_FIELDS,
            "type": expected_type,
            "query": "foo bar" if querystring != '"a"' else "a",
        }
        assert query_dict["suggest"] == {
            "name_suggestion": {"text": querystring, "term": {"field": "name"}}
        }
        assert "sort" not in query_dict  # default "relevance" mode does no sorting

    def test_single_not_quoted_character(self):
        es = Search()
        querystring = "a"

        query = queries.get_es_query(es, querystring, "", [])

        query_dict = query.to_dict()
        must_params = query_dict["query"]["bool"]["must"]
        assert len(must_params) == 1
        assert must_params[0]["multi_match"] == {
            "fields": EXPECTED_SEARCH_FIELDS,
            "type": "best_fields",
            "query": "a",
        }
        assert query_dict["suggest"] == {
            "name_suggestion": {"text": querystring, "term": {"field": "name"}}
        }
        assert "sort" not in query_dict  # default "relevance" mode does no sorting

    def test_mixed_quoted_query(self):
        es = Search()
        querystring = '"foo bar" baz'

        query = queries.get_es_query(es, querystring, "", [])

        query_dict = query.to_dict()
        assert len(query_dict["query"]["bool"]["should"]) == 2
        assert query_dict["query"]["bool"]["should"][1] == {
            "prefix": {"normalized_name": '"foo bar" baz'}
        }
        must_params = query_dict["query"]["bool"]["should"][0]["bool"]["must"]
        assert len(must_params) == 2
        assert must_params[0]["multi_match"] == {
            "fields": EXPECTED_SEARCH_FIELDS,
            "type": "phrase",
            "query": "foo bar",
        }
        assert must_params[1]["multi_match"] == {
            "fields": EXPECTED_SEARCH_FIELDS,
            "type": "best_fields",
            "query": "baz",
        }
        assert query_dict["suggest"] == {
            "name_suggestion": {"text": querystring, "term": {"field": "name"}}
        }
        assert "sort" not in query_dict  # default "relevance" mode does no sorting

    @pytest.mark.parametrize(
        "order,field", [("created", "created"), ("-zscore", "zscore")]
    )
    def test_sort_order(self, order, field):
        es = Search()
        querystring = "foo bar"

        query = queries.get_es_query(es, querystring, order, [])

        query_dict = query.to_dict()
        assert len(query_dict["query"]["bool"]["should"]) == 2
        assert query_dict["query"]["bool"]["should"][1] == {
            "prefix": {"normalized_name": "foo bar"}
        }
        must_params = query_dict["query"]["bool"]["should"][0]["bool"]["must"]
        assert len(must_params) == 1
        assert must_params[0]["multi_match"] == {
            "fields": EXPECTED_SEARCH_FIELDS,
            "type": "best_fields",
            "query": "foo bar",
        }
        assert query_dict["suggest"] == {
            "name_suggestion": {"text": querystring, "term": {"field": "name"}}
        }
        assert query_dict["sort"] == [
            {
                field: {
                    "order": "desc" if order.startswith("-") else "asc",
                    "unmapped_type": "long",
                }
            }
        ]

    @pytest.mark.parametrize("order", ["-", ""])
    def test_downloads_last_30_days_order(self, order):
        field = "downloads_last_30_days"
        es = Search()
        querystring = "foo bar"

        query = queries.get_es_query(es, querystring, f"{order}{field}", [])

        query_dict = query.to_dict()
        assert query_dict["query"]["function_score"]["functions"] == [
            {
                "field_value_factor": {
                    "field": "downloads_last_30_days",
                    "modifier": "sqrt",
                    "factor": 0.0001,
                    "missing": 0,
                }
            }
        ]
        bool_query = query_dict["query"]["function_score"]["query"]["bool"]
        assert len(bool_query["should"]) == 2
        assert bool_query["should"][1] == {"prefix": {"normalized_name": "foo bar"}}
        must_params = bool_query["should"][0]["bool"]["must"]
        assert len(must_params) == 1
        assert must_params[0]["multi_match"] == {
            "fields": EXPECTED_SEARCH_FIELDS,
            "type": "best_fields",
            "query": "foo bar",
        }
        assert query_dict["suggest"] == {
            "name_suggestion": {"text": querystring, "term": {"field": "name"}}
        }
        assert query_dict["sort"] == [
            {
                field: {
                    "order": "desc" if order.startswith("-") else "asc",
                    "unmapped_type": "long",
                }
            }
        ]

    def test_with_classifiers(self):
        es = Search()
        querystring = "foo bar"
        classifiers = [("c", "foo :: bar"), ("c", "fiz :: buz")]

        query = queries.get_es_query(es, querystring, "", classifiers)

        query_dict = query.to_dict()
        assert len(query_dict["query"]["bool"]["should"]) == 2
        assert query_dict["query"]["bool"]["should"][1] == {
            "prefix": {"normalized_name": "foo bar"}
        }
        must_params = query_dict["query"]["bool"]["should"][0]["bool"]["must"]
        assert len(must_params) == 1
        assert must_params[0]["multi_match"] == {
            "fields": EXPECTED_SEARCH_FIELDS,
            "type": "best_fields",
            "query": "foo bar",
        }
        assert query_dict["suggest"] == {
            "name_suggestion": {"text": querystring, "term": {"field": "name"}}
        }
        assert "sort" not in query_dict
        assert query_dict["query"]["bool"]["must"] == [
            {"prefix": {"classifiers": classifier}} for classifier in classifiers
        ]
        assert query_dict["query"]["bool"]["minimum_should_match"] == 1
