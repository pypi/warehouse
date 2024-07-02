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

import re

from opensearchpy import Q

SEARCH_FIELDS = [
    "author",
    "author_email",
    "description",
    "download_url",
    "home_page",
    "keywords",
    "license",
    "maintainer",
    "maintainer_email",
    "normalized_name",
    "platform",
    "summary",
]
SEARCH_BOOSTS = {
    "name": 10,
    "normalized_name": 10,
    "description": 5,
    "keywords": 5,
    "summary": 5,
}
SEARCH_FILTER_ORDER = (
    "Framework",
    "Topic",
    "Development Status",
    "License",
    "Programming Language",
    "Operating System",
    "Environment",
    "Intended Audience",
    "Natural Language",
)


def get_opensearch_query(opensearch, terms, order, classifiers):
    """
    Returns an OpenSearch query from data from the request.
    """
    classifier_q = Q(
        "bool",
        # Theh results must have all selected classifiers
        must=[
            Q(
                "bool",
                should=[
                    # Term search for the exact classifier
                    Q("term", classifiers=classifier),
                    # Prefix search for potential children classifiers
                    Q("prefix", classifiers=classifier + " :: "),
                ],
            )
            for classifier in classifiers
        ],
    )
    if not terms:
        query = opensearch.query(classifier_q) if classifiers else opensearch.query()
    else:
        quoted_string, unquoted_string = filter_query(terms)
        bool_query = Q(
            "bool",
            must=[form_query("phrase", i) for i in quoted_string]
            + [form_query("best_fields", i) for i in unquoted_string]
            + ([classifier_q] if classifiers else []),
        )

        # Allow to optionally match on prefix
        # if ``q`` is longer than one character.
        if len(terms) > 1:
            bool_query = bool_query | Q("prefix", normalized_name=terms)

        query = opensearch.query(bool_query)
        query = query.suggest("name_suggestion", terms, term={"field": "name"})

    query = query_for_order(query, order)
    return query


def filter_query(s):
    """
    Filters given query with the below regex
    and returns lists of quoted and unquoted strings
    """
    matches = re.findall(r'(?:"([^"]*)")|([^"]*)', s)
    result_quoted = [t[0].strip() for t in matches if t[0]]
    result_unquoted = [t[1].strip() for t in matches if t[1]]
    return result_quoted, result_unquoted


def form_query(query_type, query):
    """
    Returns a multi match query
    """
    fields = [
        field + "^" + str(SEARCH_BOOSTS[field]) if field in SEARCH_BOOSTS else field
        for field in SEARCH_FIELDS
    ]
    return Q("multi_match", fields=fields, query=query, type=query_type)


def query_for_order(query, order):
    """
    Applies transformations on the ES query based on the search order.

    Order is assumed to be a string with the name of a field with an optional
    hyphen to indicate descending sort order.
    """
    if order == "":  # relevance should not sort
        return query

    field = order[order.find("-") + 1 :]
    sort_info = {
        field: {
            "order": "desc" if order.startswith("-") else "asc",
            "unmapped_type": "long",
        }
    }
    query = query.sort(sort_info)
    return query
