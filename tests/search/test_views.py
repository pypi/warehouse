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


def test_search_invalid_doctype():
    app = pretend.stub(search=pretend.stub(types={}))

    with pytest.raises(NotFound):
        search(app, pretend.stub(), "fake")


def test_search_page_invalid_page():
    app = pretend.stub(
        search=pretend.stub(types={"fake": pretend.stub(SEARCH_LIMIT=25)}),
    )
    request = pretend.stub(args={"q": "Django", "page": "abc"})

    with pytest.raises(NotFound):
        search(app, request, "fake")


def test_search(monkeypatch):
    response = pretend.stub()
    render_response = pretend.call_recorder(lambda *a, **kw: response)

    monkeypatch.setattr(views, "render_response", render_response)

    app = pretend.stub(
        search=pretend.stub(
            types={
                "fake": pretend.stub(
                    SEARCH_LIMIT=25,
                    search=pretend.call_recorder(
                        lambda q, l, o: {"hits": {"hits": []}},
                    ),
                ),
            },
        ),
    )

    request = pretend.stub(args={"q": "Django"})

    resp = search(app, request, "fake")

    assert resp is response
    assert app.search.types["fake"].search.calls == [
        pretend.call("Django", 25, 0),
    ]
    assert render_response.calls == [
        pretend.call(
            app,
            request,
            "search/results.html",
            query="Django",
            total=0,
            pages=mock.ANY,
            results=[],
        ),
    ]


def test_search_page_less_than_zero(monkeypatch):
    response = pretend.stub()
    render_response = pretend.call_recorder(lambda *a, **kw: response)

    monkeypatch.setattr(views, "render_response", render_response)

    app = pretend.stub(
        search=pretend.stub(
            types={
                "fake": pretend.stub(
                    SEARCH_LIMIT=25,
                    search=pretend.call_recorder(
                        lambda q, l, o: {"hits": {"hits": []}},
                    ),
                ),
            },
        ),
    )

    request = pretend.stub(args={"q": "Django", "page": "-1"})

    resp = search(app, request, "fake")

    assert resp is response
    assert app.search.types["fake"].search.calls == [
        pretend.call("Django", 25, 0),
    ]
    assert render_response.calls == [
        pretend.call(
            app,
            request,
            "search/results.html",
            query="Django",
            total=0,
            pages=mock.ANY,
            results=[],
        ),
    ]
