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

from unittest import mock

from werkzeug.exceptions import NotFound
import pretend
import pytest

from warehouse.search import views
from warehouse.search.views import search


def test_search_invalid_doctype(warehouse_app):
    with warehouse_app.test_request_context():
        with pytest.raises(NotFound):
            search("fake")


def test_search_page_invalid_page(warehouse_app):
    with warehouse_app.test_request_context(
            query_string={"q": "Django", "page": "abc"}):
        warehouse_app.search.types = {"fake": pretend.stub(SEARCH_LIMIT=25)}
        with pytest.raises(NotFound):
            search("fake")


def test_search(monkeypatch, warehouse_app):
    response = pretend.stub()
    render_template = pretend.call_recorder(lambda *a, **kw: response)

    monkeypatch.setattr(views, "render_template", render_template)

    warehouse_app.search = pretend.stub(
        types={
            "fake": pretend.stub(
                SEARCH_LIMIT=25,
                search=pretend.call_recorder(
                    lambda q, l, o: {"hits": {"hits": []}},
                ),
            ),
        },
    )

    with warehouse_app.test_request_context(query_string={"q": "Django"}):
        resp = search("fake")

    assert resp is response
    assert warehouse_app.search.types["fake"].search.calls == [
        pretend.call("Django", 25, 0),
    ]
    assert render_template.calls == [
        pretend.call(
            "search/results.html",
            query="Django",
            total=0,
            pages=mock.ANY,
            results=[],
        ),
    ]


def test_search_page_less_than_zero(monkeypatch, warehouse_app):
    response = pretend.stub()
    render_template = pretend.call_recorder(lambda *a, **kw: response)

    monkeypatch.setattr(views, "render_template", render_template)

    warehouse_app.search = pretend.stub(
        types={
            "fake": pretend.stub(
                SEARCH_LIMIT=25,
                search=pretend.call_recorder(
                    lambda q, l, o: {"hits": {"hits": []}},
                ),
            ),
        },
    )

    with warehouse_app.test_request_context(
            query_string={"q": "Django", "page": "-1"}):
        resp = search("fake")

    assert resp is response
    assert warehouse_app.search.types["fake"].search.calls == [
        pretend.call("Django", 25, 0),
    ]
    assert render_template.calls == [
        pretend.call(
            "search/results.html",
            query="Django",
            total=0,
            pages=mock.ANY,
            results=[],
        ),
    ]
