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

import elasticsearch
import pretend
import pytest

from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPNotFound,
    HTTPSeeOther,
    HTTPServiceUnavailable,
)
from trove_classifiers import sorted_classifiers
from webob.multidict import MultiDict

from warehouse import views
from warehouse.views import (
    current_user_indicator,
    flash_messages,
    forbidden,
    forbidden_include,
    force_status,
    health,
    httpexception_view,
    index,
    list_classifiers,
    locale,
    opensearchxml,
    robotstxt,
    search,
    service_unavailable,
    session_notifications,
    stats,
)

from ..common.db.accounts import UserFactory
from ..common.db.classifiers import ClassifierFactory
from ..common.db.packaging import FileFactory, ProjectFactory, ReleaseFactory


class TestHTTPExceptionView:
    def test_returns_context_when_no_template(self, pyramid_config):
        pyramid_config.testing_add_renderer("non-existent.html")

        response = context = pretend.stub(status_code=499)
        request = pretend.stub()
        assert httpexception_view(context, request) is response

    @pytest.mark.parametrize("status_code", [403, 404, 410, 500])
    def test_renders_template(self, pyramid_config, status_code):
        renderer = pyramid_config.testing_add_renderer("{}.html".format(status_code))

        context = pretend.stub(
            status="{} My Cool Status".format(status_code),
            status_code=status_code,
            headers={},
        )
        request = pretend.stub()
        response = httpexception_view(context, request)

        assert response.status_code == status_code
        assert response.status == "{} My Cool Status".format(status_code)
        renderer.assert_()

    @pytest.mark.parametrize("status_code", [403, 404, 410, 500])
    def test_renders_template_with_headers(self, pyramid_config, status_code):
        renderer = pyramid_config.testing_add_renderer("{}.html".format(status_code))

        context = pretend.stub(
            status="{} My Cool Status".format(status_code),
            status_code=status_code,
            headers={"Foo": "Bar"},
        )
        request = pretend.stub()
        response = httpexception_view(context, request)

        assert response.status_code == status_code
        assert response.status == "{} My Cool Status".format(status_code)
        assert response.headers["Foo"] == "Bar"
        renderer.assert_()

    def test_renders_404_with_csp(self, pyramid_config):
        renderer = pyramid_config.testing_add_renderer("404.html")

        csp = {}
        services = {"csp": pretend.stub(merge=csp.update)}

        context = HTTPNotFound()
        request = pretend.stub(find_service=lambda name: services[name], path="")
        response = httpexception_view(context, request)

        assert response.status_code == 404
        assert response.status == "404 Not Found"
        assert csp == {
            "frame-src": ["https://www.youtube-nocookie.com"],
            "script-src": ["https://www.youtube.com", "https://s.ytimg.com"],
        }
        renderer.assert_()

    def test_simple_404(self):
        csp = {}
        services = {"csp": pretend.stub(merge=csp.update)}
        context = HTTPNotFound()
        for path in ("/simple/not_found_package", "/simple/some/unusual/path/"):
            request = pretend.stub(find_service=lambda name: services[name], path=path)
            response = httpexception_view(context, request)
            assert response.status_code == 404
            assert response.status == "404 Not Found"
            assert response.content_type == "text/plain"
            assert response.text == "404 Not Found"


class TestForbiddenView:
    def test_logged_in_returns_exception(self, pyramid_config):
        renderer = pyramid_config.testing_add_renderer("403.html")

        exc = pretend.stub(status_code=403, status="403 Forbidden", headers={})
        request = pretend.stub(authenticated_userid=1)
        resp = forbidden(exc, request)
        assert resp.status_code == 403
        renderer.assert_()

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
        assert resp.headers["Location"] == "/accounts/login/?next=/foo/bar/%3Fb%3Ds"


class TestForbiddenIncludeView:
    def test_forbidden_include(self):
        exc = pretend.stub()
        request = pretend.stub()

        resp = forbidden_include(exc, request)

        assert resp.status_code == 403
        assert resp.content_type == "text/html"
        assert resp.content_length == 0


class TestServiceUnavailableView:
    def test_renders_503(self, pyramid_config, pyramid_request):
        renderer = pyramid_config.testing_add_renderer("503.html")
        renderer.string_response = "A 503 Error"

        resp = service_unavailable(pretend.stub(), pyramid_request)

        assert resp.status_code == 503
        assert resp.content_type == "text/html"
        assert resp.body == b"A 503 Error"


def test_robotstxt(pyramid_request):
    assert robotstxt(pyramid_request) == {}
    assert pyramid_request.response.content_type == "text/plain"


def test_opensearchxml(pyramid_request):
    assert opensearchxml(pyramid_request) == {}
    assert pyramid_request.response.content_type == "text/xml"


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
            "latest_releases": [release2, release1],
            "trending_projects": [release2],
            "num_projects": 1,
            "num_users": 3,
            "num_releases": 2,
            "num_files": 1,
        }


class TestLocale:
    @pytest.mark.parametrize(
        ("referer", "redirect", "get", "valid"),
        [
            (None, "/fake-route", {"locale_id": "en"}, True),
            ("http://example.com", "/fake-route", {"nonsense": "arguments"}, False),
            ("/robots.txt", "/robots.txt", {"locale_id": "non-existent-locale"}, False),
        ],
    )
    def test_locale(self, referer, redirect, get, valid, monkeypatch):
        localizer = pretend.stub(translate=lambda *a: "translated")
        make_localizer = pretend.call_recorder(lambda *a: localizer)
        monkeypatch.setattr(views, "make_localizer", make_localizer)
        tdirs = pretend.stub()
        request = pretend.stub(
            GET=get,
            referer=referer,
            route_path=pretend.call_recorder(lambda r: "/fake-route"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            host=None,
            registry=pretend.stub(queryUtility=lambda *a: tdirs),
        )

        result = locale(request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == redirect

        if valid:
            assert "Set-Cookie" in result.headers
            assert f"_LOCALE_={get['locale_id']};" in result.headers["Set-Cookie"]
            assert make_localizer.calls == [pretend.call(get["locale_id"], tdirs)]
            assert request.session.flash.calls == [
                pretend.call("translated", queue="success")
            ]
        else:
            assert "Set-Cookie" not in result.headers


def test_esi_current_user_indicator():
    assert current_user_indicator(pretend.stub()) == {}


def test_esi_flash_messages():
    assert flash_messages(pretend.stub()) == {}


def test_esi_session_notifications():
    assert session_notifications(pretend.stub()) == {}


class TestSearch:
    @pytest.mark.parametrize("page", [None, 1, 5])
    def test_with_a_query(self, monkeypatch, db_request, metrics, page):
        params = MultiDict({"q": "foo bar"})
        if page is not None:
            params["page"] = page
        db_request.params = params

        db_request.es = pretend.stub()
        es_query = pretend.stub()
        get_es_query = pretend.call_recorder(lambda *a, **kw: es_query)
        monkeypatch.setattr(views, "get_es_query", get_es_query)

        page_obj = pretend.stub(page_count=(page or 1) + 10, item_count=1000)
        page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
        monkeypatch.setattr(views, "ElasticsearchPage", page_cls)

        url_maker = pretend.stub()
        url_maker_factory = pretend.call_recorder(lambda request: url_maker)
        monkeypatch.setattr(views, "paginate_url_factory", url_maker_factory)

        assert search(db_request) == {
            "page": page_obj,
            "term": params.get("q", ""),
            "order": "",
            "applied_filters": [],
            "available_filters": [],
        }
        assert get_es_query.calls == [
            pretend.call(db_request.es, params.get("q"), "", [])
        ]
        assert page_cls.calls == [
            pretend.call(es_query, url_maker=url_maker, page=page or 1)
        ]
        assert url_maker_factory.calls == [pretend.call(db_request)]
        assert metrics.histogram.calls == [
            pretend.call("warehouse.views.search.results", 1000)
        ]

    @pytest.mark.parametrize("page", [None, 1, 5])
    def test_with_classifiers(self, monkeypatch, db_request, metrics, page):
        params = MultiDict([("q", "foo bar"), ("c", "foo :: bar"), ("c", "fiz :: buz")])
        if page is not None:
            params["page"] = page
        db_request.params = params

        es_query = pretend.stub()
        db_request.es = pretend.stub()
        get_es_query = pretend.call_recorder(lambda *a, **kw: es_query)
        monkeypatch.setattr(views, "get_es_query", get_es_query)

        classifier1 = ClassifierFactory.create(classifier="foo :: bar")
        classifier2 = ClassifierFactory.create(classifier="foo :: baz")
        classifier3 = ClassifierFactory.create(classifier="fiz :: buz")

        project = ProjectFactory.create()
        release1 = ReleaseFactory.create(project=project)
        release1.created = datetime.date(2011, 1, 1)
        release1._classifiers.append(classifier1)
        release1._classifiers.append(classifier2)

        page_obj = pretend.stub(page_count=(page or 1) + 10, item_count=1000)
        page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
        monkeypatch.setattr(views, "ElasticsearchPage", page_cls)

        url_maker = pretend.stub()
        url_maker_factory = pretend.call_recorder(lambda request: url_maker)
        monkeypatch.setattr(views, "paginate_url_factory", url_maker_factory)

        search_view = search(db_request)
        assert search_view == {
            "page": page_obj,
            "term": params.get("q", ""),
            "order": "",
            "applied_filters": params.getall("c"),
            "available_filters": [
                {
                    "foo": {
                        classifier1.classifier.split(" :: ")[1]: {},
                        classifier2.classifier.split(" :: ")[1]: {},
                    }
                }
            ],
        }
        assert ("fiz", [classifier3.classifier]) not in search_view["available_filters"]
        assert page_cls.calls == [
            pretend.call(es_query, url_maker=url_maker, page=page or 1)
        ]
        assert url_maker_factory.calls == [pretend.call(db_request)]
        assert get_es_query.calls == [
            pretend.call(db_request.es, params.get("q"), "", params.getall("c"))
        ]
        assert metrics.histogram.calls == [
            pretend.call("warehouse.views.search.results", 1000)
        ]

    def test_returns_404_with_pagenum_too_high(self, monkeypatch, db_request, metrics):
        params = MultiDict({"page": 15})
        db_request.params = params

        es_query = pretend.stub()
        db_request.es = pretend.stub(query=lambda *a, **kw: es_query)

        page_obj = pretend.stub(page_count=10, item_count=1000)
        page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
        monkeypatch.setattr(views, "ElasticsearchPage", page_cls)

        url_maker = pretend.stub()
        url_maker_factory = pretend.call_recorder(lambda request: url_maker)
        monkeypatch.setattr(views, "paginate_url_factory", url_maker_factory)

        with pytest.raises(HTTPNotFound):
            search(db_request)

        assert page_cls.calls == [
            pretend.call(es_query, url_maker=url_maker, page=15 or 1)
        ]
        assert url_maker_factory.calls == [pretend.call(db_request)]
        assert metrics.histogram.calls == []

    def test_raises_400_with_pagenum_type_str(self, monkeypatch, db_request, metrics):
        params = MultiDict({"page": "abc"})
        db_request.params = params

        es_query = pretend.stub()
        db_request.es = pretend.stub(query=lambda *a, **kw: es_query)

        page_obj = pretend.stub(page_count=10, item_count=1000)
        page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
        monkeypatch.setattr(views, "ElasticsearchPage", page_cls)

        url_maker = pretend.stub()
        url_maker_factory = pretend.call_recorder(lambda request: url_maker)
        monkeypatch.setattr(views, "paginate_url_factory", url_maker_factory)

        with pytest.raises(HTTPBadRequest):
            search(db_request)

        assert page_cls.calls == []
        assert metrics.histogram.calls == []

    def test_returns_503_when_es_unavailable(self, monkeypatch, db_request, metrics):
        params = MultiDict({"page": 15})
        db_request.params = params

        es_query = pretend.stub()
        db_request.es = pretend.stub(query=lambda *a, **kw: es_query)

        def raiser(*args, **kwargs):
            raise elasticsearch.ConnectionError()

        monkeypatch.setattr(views, "ElasticsearchPage", raiser)

        url_maker = pretend.stub()
        url_maker_factory = pretend.call_recorder(lambda request: url_maker)
        monkeypatch.setattr(views, "paginate_url_factory", url_maker_factory)

        with pytest.raises(HTTPServiceUnavailable):
            search(db_request)

        assert url_maker_factory.calls == [pretend.call(db_request)]
        assert metrics.increment.calls == [pretend.call("warehouse.views.search.error")]
        assert metrics.histogram.calls == []


def test_classifiers(db_request):
    assert list_classifiers(db_request) == {"classifiers": sorted_classifiers}


def test_stats(db_request):
    project = ProjectFactory.create()
    release1 = ReleaseFactory.create(project=project)
    release1.created = datetime.date(2011, 1, 1)
    FileFactory.create(
        release=release1,
        filename="{}-{}.tar.gz".format(project.name, release1.version),
        python_version="source",
        size=69,
    )
    assert stats(db_request) == {
        "total_packages_size": 69,
        "top_packages": {project.name: {"size": 69}},
    }


def test_health():
    request = pretend.stub(
        db=pretend.stub(execute=pretend.call_recorder(lambda q: None))
    )

    assert health(request) == "OK"
    assert request.db.execute.calls == [pretend.call("SELECT 1")]


class TestForceStatus:
    def test_valid(self):
        with pytest.raises(HTTPBadRequest):
            force_status(pretend.stub(matchdict={"status": "400"}))

    def test_invalid(self):
        with pytest.raises(HTTPNotFound):
            force_status(pretend.stub(matchdict={"status": "599"}))
