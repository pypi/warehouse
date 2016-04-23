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

import datetime

import pretend
import pytest
from webob.multidict import MultiDict

from pyramid.httpexceptions import HTTPNotFound

from warehouse import views
from warehouse.views import (
    forbidden, index, httpexception_view, robotstxt, current_user_indicator,
    search, health
)

from ..common.db.accounts import UserFactory
from ..common.db.classifiers import ClassifierFactory
from ..common.db.packaging import (
    ProjectFactory, ReleaseFactory, FileFactory,
)


def test_httpexception_view():
    response = context = pretend.stub()
    request = pretend.stub()
    assert httpexception_view(context, request) is response


class TestForbiddenView:

    def test_logged_in_returns_exception(self):
        exc, request = pretend.stub(), pretend.stub(authenticated_userid=1)
        resp = forbidden(exc, request)
        assert resp is exc

    def test_logged_out_redirects_login(self):
        exc = pretend.stub()
        request = pretend.stub(
            authenticated_userid=None,
            path_qs="/foo/bar/?b=s",
            route_url=pretend.call_recorder(
                lambda route, _query: "/accounts/login/?next=/foo/bar/%3Fb%3Ds"
            ),
        )

        resp = forbidden(exc, request)

        assert resp.status_code == 303
        assert resp.headers["Location"] == \
            "/accounts/login/?next=/foo/bar/%3Fb%3Ds"


def test_robotstxt(pyramid_request):
    assert robotstxt(pyramid_request) == {}
    assert pyramid_request.response.content_type == "text/plain"


class TestIndex:

    def test_index(self, db_request):

        project = ProjectFactory.create()
        release1 = ReleaseFactory.create(project=project)
        release1.created = datetime.date(2011, 1, 1)
        release2 = ReleaseFactory.create(project=project)
        release2.created = datetime.date(2012, 1, 1)
        FileFactory.create(
            release=release1,
            filename="{}-{}.tar.gz".format(project.name, release1.version),
            python_version="source",
        )
        UserFactory.create()

        assert index(db_request) == {
            # assert that ordering is correct
            'latest_releases': [release2, release1],
            'top_projects': [release2],
            'num_projects': 1,
            'num_users': 3,
            'num_releases': 2,
            'num_files': 1,
        }


def test_esi_current_user_indicator():
    assert current_user_indicator(pretend.stub()) == {}


class TestSearch:

    @pytest.mark.parametrize("page", [None, 1, 5])
    def test_with_a_query(self, monkeypatch, db_request, page):
        params = MultiDict({"q": "foo bar"})
        if page is not None:
            params["page"] = page
        db_request.params = params

        sort = pretend.stub()
        suggest = pretend.stub(
            sort=pretend.call_recorder(lambda *a, **kw: sort),
        )
        es_query = pretend.stub(
            suggest=pretend.call_recorder(lambda *a, **kw: suggest),
        )
        db_request.es = pretend.stub(
            query=pretend.call_recorder(lambda *a, **kw: es_query)
        )

        page_obj = pretend.stub(page_count=(page or 1) + 10)
        page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
        monkeypatch.setattr(views, "ElasticsearchPage", page_cls)

        url_maker = pretend.stub()
        url_maker_factory = pretend.call_recorder(lambda request: url_maker)
        monkeypatch.setattr(views, "paginate_url_factory", url_maker_factory)

        assert search(db_request) == {
            "page": page_obj,
            "term": params.get("q", ''),
            "order": params.get("o", ''),
            "applied_filters": [],
            "available_filters": [],
        }
        assert page_cls.calls == [
            pretend.call(suggest, url_maker=url_maker, page=page or 1),
        ]
        assert url_maker_factory.calls == [pretend.call(db_request)]
        assert db_request.es.query.calls == [
            pretend.call(
                "multi_match",
                query="foo bar",
                fields=[
                    "name^2", "version", "author", "author_email",
                    "maintainer", "maintainer_email", "home_page", "license",
                    "summary", "description", "keywords", "platform",
                    "download_url",
                ],
            ),
        ]
        assert es_query.suggest.calls == [
            pretend.call(
                name="name_suggestion",
                term={"field": "name"},
                text="foo bar",
            ),
        ]

    @pytest.mark.parametrize("page", [None, 1, 5])
    def test_with_an_ordering(self, monkeypatch, db_request, page):
        params = MultiDict({"q": "foo bar", "o": "-created"})
        if page is not None:
            params["page"] = page
        db_request.params = params

        sort = pretend.stub()
        suggest = pretend.stub(
            sort=pretend.call_recorder(lambda *a, **kw: sort),
        )
        es_query = pretend.stub(
            suggest=pretend.call_recorder(lambda *a, **kw: suggest),
        )
        db_request.es = pretend.stub(
            query=pretend.call_recorder(lambda *a, **kw: es_query)
        )

        page_obj = pretend.stub(page_count=(page or 1) + 10)
        page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
        monkeypatch.setattr(views, "ElasticsearchPage", page_cls)

        url_maker = pretend.stub()
        url_maker_factory = pretend.call_recorder(lambda request: url_maker)
        monkeypatch.setattr(views, "paginate_url_factory", url_maker_factory)

        assert search(db_request) == {
            "page": page_obj,
            "term": params.get("q", ''),
            "order": params.get("o", ''),
            "applied_filters": [],
            "available_filters": [],
        }
        assert page_cls.calls == [
            pretend.call(sort, url_maker=url_maker, page=page or 1),
        ]
        assert url_maker_factory.calls == [pretend.call(db_request)]
        assert db_request.es.query.calls == [
            pretend.call(
                "multi_match",
                query="foo bar",
                fields=[
                    "name^2", "version", "author", "author_email",
                    "maintainer", "maintainer_email", "home_page", "license",
                    "summary", "description", "keywords", "platform",
                    "download_url",
                ],
            ),
        ]
        assert es_query.suggest.calls == [
            pretend.call(
                name="name_suggestion",
                term={"field": "name"},
                text="foo bar",
            ),
        ]
        assert suggest.sort.calls == [
            pretend.call("-created")
        ]

    @pytest.mark.parametrize("page", [None, 1, 5])
    def test_with_classifiers(self, monkeypatch, db_request, page):
        params = MultiDict([
            ("q", "foo bar"),
            ("c", "foo :: bar"),
            ("c", "fiz :: buz"),
        ])
        if page is not None:
            params["page"] = page
        db_request.params = params

        es_query = pretend.stub(
            suggest=pretend.call_recorder(lambda *a, **kw: es_query),
            filter=pretend.call_recorder(lambda *a, **kw: es_query),
            sort=pretend.call_recorder(lambda *a, **kw: es_query),
        )
        db_request.es = pretend.stub(
            query=pretend.call_recorder(lambda *a, **kw: es_query)
        )

        classifier1 = ClassifierFactory.create(classifier="foo :: bar")
        classifier2 = ClassifierFactory.create(classifier="foo :: baz")
        classifier3 = ClassifierFactory.create(classifier="fiz :: buz")

        page_obj = pretend.stub(page_count=(page or 1) + 10)
        page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
        monkeypatch.setattr(views, "ElasticsearchPage", page_cls)

        url_maker = pretend.stub()
        url_maker_factory = pretend.call_recorder(lambda request: url_maker)
        monkeypatch.setattr(views, "paginate_url_factory", url_maker_factory)

        assert search(db_request) == {
            "page": page_obj,
            "term": params.get("q", ''),
            "order": params.get("o", ''),
            "applied_filters": params.getall("c"),
            "available_filters": [
                ('fiz', [classifier3.classifier]),
                ('foo', [
                    classifier1.classifier,
                    classifier2.classifier,
                ])
            ],
        }
        assert page_cls.calls == [
            pretend.call(es_query, url_maker=url_maker, page=page or 1),
        ]
        assert url_maker_factory.calls == [pretend.call(db_request)]
        assert db_request.es.query.calls == [
            pretend.call(
                "multi_match",
                query="foo bar",
                fields=[
                    "name^2", "version", "author", "author_email",
                    "maintainer", "maintainer_email", "home_page", "license",
                    "summary", "description", "keywords", "platform",
                    "download_url",
                ],
            ),
        ]
        assert es_query.suggest.calls == [
            pretend.call(
                name="name_suggestion",
                term={"field": "name"},
                text="foo bar",
            ),
        ]
        assert es_query.filter.calls == [
            pretend.call('terms', classifiers=['foo :: bar', 'fiz :: buz'])
        ]

    @pytest.mark.parametrize("page", [None, 1, 5])
    def test_without_a_query(self, monkeypatch, db_request, page):
        params = MultiDict()
        if page is not None:
            params["page"] = page
        db_request.params = params

        es_query = pretend.stub()
        db_request.es = pretend.stub(query=lambda *a, **kw: es_query)

        page_obj = pretend.stub(page_count=(page or 1) + 10)
        page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
        monkeypatch.setattr(views, "ElasticsearchPage", page_cls)

        url_maker = pretend.stub()
        url_maker_factory = pretend.call_recorder(lambda request: url_maker)
        monkeypatch.setattr(views, "paginate_url_factory", url_maker_factory)

        assert search(db_request) == {
            "page": page_obj,
            "term": params.get("q", ''),
            "order": params.get("o", ''),
            "applied_filters": [],
            "available_filters": [],
        }
        assert page_cls.calls == [
            pretend.call(es_query, url_maker=url_maker, page=page or 1),
        ]
        assert url_maker_factory.calls == [pretend.call(db_request)]

    def test_raises_404_with_pagenum_too_high(self, monkeypatch, db_request):
        params = MultiDict({"page": 15})
        db_request.params = params

        es_query = pretend.stub()
        db_request.es = pretend.stub(query=lambda *a, **kw: es_query)

        page_obj = pretend.stub(page_count=10)
        page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
        monkeypatch.setattr(views, "ElasticsearchPage", page_cls)

        url_maker = pretend.stub()
        url_maker_factory = pretend.call_recorder(lambda request: url_maker)
        monkeypatch.setattr(views, "paginate_url_factory", url_maker_factory)

        with pytest.raises(HTTPNotFound):
            search(db_request)

        assert page_cls.calls == [
            pretend.call(es_query, url_maker=url_maker, page=15 or 1),
        ]
        assert url_maker_factory.calls == [pretend.call(db_request)]


def test_health():
    request = pretend.stub(
        db=pretend.stub(
            execute=pretend.call_recorder(lambda q: None),
        ),
    )

    assert health(request) == "OK"
    assert request.db.execute.calls == [pretend.call("SELECT 1")]
