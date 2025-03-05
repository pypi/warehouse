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

from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound

from warehouse.admin.views import namespaces as views

from ....common.db.organizations import NamespaceFactory


class TestNamespaceList:

    def test_no_query(self, db_request):
        namespaces = sorted(
            NamespaceFactory.create_batch(30), key=lambda n: n.normalized_name
        )
        result = views.namespace_list(db_request)

        assert result == {"namespaces": namespaces[:25], "query": "", "terms": []}

    def test_with_page(self, db_request):
        db_request.GET["page"] = "2"
        namespaces = sorted(
            NamespaceFactory.create_batch(30), key=lambda n: n.normalized_name
        )
        result = views.namespace_list(db_request)

        assert result == {"namespaces": namespaces[25:], "query": "", "terms": []}

    def test_with_invalid_page(self):
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda *a: False),
            params={"page": "not an integer"},
        )

        with pytest.raises(HTTPBadRequest):
            views.namespace_list(request)

    def test_basic_query(self, db_request):
        namespaces = sorted(
            NamespaceFactory.create_batch(5), key=lambda n: n.normalized_name
        )
        db_request.GET["q"] = namespaces[0].name
        result = views.namespace_list(db_request)

        assert namespaces[0] in result["namespaces"]
        assert result["query"] == namespaces[0].name
        assert result["terms"] == [namespaces[0].name]

    def test_name_query(self, db_request):
        namespaces = sorted(
            NamespaceFactory.create_batch(5), key=lambda n: n.normalized_name
        )
        db_request.GET["q"] = f"name:{namespaces[0].name}"
        result = views.namespace_list(db_request)

        assert namespaces[0] in result["namespaces"]
        assert result["query"] == f"name:{namespaces[0].name}"
        assert result["terms"] == [f"name:{namespaces[0].name}"]

    def test_organization_query(self, db_request):
        namespaces = sorted(
            NamespaceFactory.create_batch(5), key=lambda n: n.normalized_name
        )
        db_request.GET["q"] = f"organization:{namespaces[0].owner.name}"
        result = views.namespace_list(db_request)

        assert namespaces[0] in result["namespaces"]
        assert result["query"] == f"organization:{namespaces[0].owner.name}"
        assert result["terms"] == [f"organization:{namespaces[0].owner.name}"]

    def test_is_approved_query(self, db_request):
        namespaces = sorted(
            NamespaceFactory.create_batch(5), key=lambda n: n.normalized_name
        )
        namespaces[0].is_approved = True
        namespaces[1].is_approved = True
        namespaces[2].is_approved = False
        namespaces[3].is_approved = False
        namespaces[4].is_approved = False
        db_request.GET["q"] = "is:approved"
        result = views.namespace_list(db_request)

        assert result == {
            "namespaces": namespaces[:2],
            "query": "is:approved",
            "terms": ["is:approved"],
        }

    def test_is_pending_query(self, db_request):
        namespaces = sorted(
            NamespaceFactory.create_batch(5), key=lambda n: n.normalized_name
        )
        namespaces[0].is_approved = True
        namespaces[1].is_approved = True
        namespaces[2].is_approved = False
        namespaces[3].is_approved = False
        namespaces[4].is_approved = False
        db_request.GET["q"] = "is:pending"
        result = views.namespace_list(db_request)

        assert result == {
            "namespaces": namespaces[2:],
            "query": "is:pending",
            "terms": ["is:pending"],
        }

    def test_is_invalid_query(self, db_request):
        namespaces = sorted(
            NamespaceFactory.create_batch(5), key=lambda n: n.normalized_name
        )
        db_request.GET["q"] = "is:not-actually-a-valid-query"
        result = views.namespace_list(db_request)

        assert result == {
            "namespaces": namespaces[:25],
            "query": "is:not-actually-a-valid-query",
            "terms": ["is:not-actually-a-valid-query"],
        }


class TestNamespaceDetail:
    def test_detail(self, db_request):
        namespaces = sorted(
            NamespaceFactory.create_batch(5), key=lambda n: n.normalized_name
        )
        db_request.matchdict["namespace_id"] = str(namespaces[1].id)

        assert views.namespace_detail(db_request) == {
            "namespace": namespaces[1],
        }

    def test_detail_not_found(self, db_request):
        NamespaceFactory.create_batch(5)
        db_request.matchdict["namespace_id"] = "c6a1a66b-d1af-45fc-ae9f-21b36662c2ac"

        with pytest.raises(HTTPNotFound):
            views.namespace_detail(db_request)
