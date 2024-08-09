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

import opensearchpy
import pretend
import pytest
import sqlalchemy

from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPNotFound,
    HTTPRequestEntityTooLarge,
    HTTPSeeOther,
    HTTPServiceUnavailable,
)
from trove_classifiers import sorted_classifiers
from webob.multidict import MultiDict

from warehouse import views
from warehouse.errors import WarehouseDenied
from warehouse.packaging.models import ProjectFactory as DBProjectFactory
from warehouse.utils.row_counter import compute_row_counts
from warehouse.views import (
    SecurityKeyGiveaway,
    current_user_indicator,
    flash_messages,
    forbidden,
    forbidden_api,
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
    sidebar_sponsor_logo,
    stats,
)

from ..common.db.accounts import UserFactory
from ..common.db.classifiers import ClassifierFactory
from ..common.db.packaging import FileFactory, ProjectFactory, ReleaseFactory


class TestHTTPExceptionView:
    def test_returns_context_when_no_template(self, pyramid_config):
        pyramid_config.testing_add_renderer("non-existent.html")

        response = context = pretend.stub(status_code=499)
        request = pretend.stub(context=None)
        assert httpexception_view(context, request) is response

    @pytest.mark.parametrize("status_code", [403, 404, 410, 500])
    def test_renders_template(self, pyramid_config, status_code):
        renderer = pyramid_config.testing_add_renderer(f"{status_code}.html")

        context = pretend.stub(
            status=f"{status_code} My Cool Status",
            status_code=status_code,
            headers={},
        )
        request = pretend.stub(context=None)
        response = httpexception_view(context, request)

        assert response.status_code == status_code
        assert response.status == f"{status_code} My Cool Status"
        renderer.assert_()

    @pytest.mark.parametrize("status_code", [403, 404, 410, 500])
    def test_renders_template_with_headers(self, pyramid_config, status_code):
        renderer = pyramid_config.testing_add_renderer(f"{status_code}.html")

        context = pretend.stub(
            status=f"{status_code} My Cool Status",
            status_code=status_code,
            headers={"Foo": "Bar"},
        )
        request = pretend.stub(context=None)
        response = httpexception_view(context, request)

        assert response.status_code == status_code
        assert response.status == f"{status_code} My Cool Status"
        assert response.headers["Foo"] == "Bar"
        renderer.assert_()

    def test_renders_404_with_csp(self, pyramid_config):
        renderer = pyramid_config.testing_add_renderer("404.html")

        csp = {}
        services = {"csp": pretend.stub(merge=csp.update)}

        context = HTTPNotFound()
        request = pretend.stub(
            find_service=lambda name: services[name], path="", context=None
        )
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
            request = pretend.stub(
                find_service=lambda name: services[name], path=path, context=None
            )
            response = httpexception_view(context, request)
            assert response.status_code == 404
            assert response.status == "404 Not Found"
            assert response.content_type == "text/plain"
            assert response.text == "404 Not Found"

    def test_json_404(self):
        csp = {}
        services = {"csp": pretend.stub(merge=csp.update)}
        context = HTTPNotFound()
        for path in (
            "/pypi/not_found_package/json",
            "/pypi/not_found_package/1.0.0/json",
        ):
            request = pretend.stub(
                find_service=lambda name: services[name], path=path, context=None
            )
            response = httpexception_view(context, request)
            assert response.status_code == 404
            assert response.status == "404 Not Found"
            assert response.content_type == "application/json"
            assert response.text == '{"message": "Not Found"}'

    def test_context_is_project(self, pyramid_config, monkeypatch):
        csp = {}
        services = {"csp": pretend.stub(merge=csp.update)}

        context = HTTPNotFound()
        project = ProjectFactory.create()
        request = pretend.stub(
            find_service=lambda name: services[name],
            path="",
            context=project,
        )
        stub_response = pretend.stub(headers=[])
        render_to_response = pretend.call_recorder(
            lambda filename, kwargs, request: stub_response
        )
        monkeypatch.setattr(views, "render_to_response", render_to_response)
        response = httpexception_view(context, request)

        assert response == stub_response
        assert render_to_response.calls == [
            pretend.call(
                "404.html",
                {"project_name": project.name},
                request=request,
            )
        ]

    def test_context_is_projectfactory(self, pyramid_config, monkeypatch):
        csp = {}
        services = {"csp": pretend.stub(merge=csp.update)}

        context = HTTPNotFound()
        request = pretend.stub(
            find_service=lambda name: services[name],
            path="",
            matchdict={"name": "missing-project"},
        )
        request.context = DBProjectFactory(request)
        stub_response = pretend.stub(headers=[])
        render_to_response = pretend.call_recorder(
            lambda filename, kwargs, request: stub_response
        )
        monkeypatch.setattr(views, "render_to_response", render_to_response)
        response = httpexception_view(context, request)

        assert response == stub_response
        assert render_to_response.calls == [
            pretend.call(
                "404.html",
                {"project_name": "missing-project"},
                request=request,
            )
        ]


class TestForbiddenView:
    def test_logged_in_returns_exception(self, pyramid_config):
        renderer = pyramid_config.testing_add_renderer("403.html")

        exc = pretend.stub(
            status_code=403, status="403 Forbidden", headers={}, result=pretend.stub()
        )
        request = pretend.stub(user=pretend.stub(), context=None)
        resp = forbidden(exc, request)
        assert resp.status_code == 403
        renderer.assert_()

    def test_logged_out_redirects_login(self):
        exc = pretend.stub()
        request = pretend.stub(
            user=None,
            path_qs="/foo/bar/?b=s",
            route_url=pretend.call_recorder(
                lambda route, _query: "/accounts/login/?next=/foo/bar/%3Fb%3Ds"
            ),
            context=None,
        )

        resp = forbidden(exc, request)

        assert resp.status_code == 303
        assert resp.headers["Location"] == "/accounts/login/?next=/foo/bar/%3Fb%3Ds"

    @pytest.mark.parametrize("reason", ("manage_2fa_required",))
    def test_two_factor_required(self, reason):
        result = WarehouseDenied("Some summary", reason=reason)
        exc = pretend.stub(result=result)
        request = pretend.stub(
            user=pretend.stub(),
            session=pretend.stub(flash=pretend.call_recorder(lambda x, queue: None)),
            path_qs="/foo/bar/?b=s",
            route_url=pretend.call_recorder(
                lambda route, _query: "/the/url/?next=/foo/bar/%3Fb%3Ds"
            ),
            _=lambda x: x,
        )

        resp = forbidden(exc, request)

        assert resp.status_code == 303
        assert resp.headers["Location"] == "/the/url/?next=/foo/bar/%3Fb%3Ds"
        assert request.route_url.calls == [
            pretend.call("manage.account.two-factor", _query={"next": "/foo/bar/?b=s"})
        ]
        assert request.session.flash.calls == [
            pretend.call(
                "Two-factor authentication must be enabled on your account to "
                "perform this action.",
                queue="error",
            )
        ]

    @pytest.mark.parametrize(
        "requested_path",
        ("/manage/projects/", "/manage/account/two-factor/", "/manage/organizations/"),
    )
    def test_unverified_email_redirects(self, requested_path):
        result = WarehouseDenied("Some summary", reason="unverified_email")
        exc = pretend.stub(result=result)
        request = pretend.stub(
            user=pretend.stub(),
            session=pretend.stub(flash=pretend.call_recorder(lambda x, queue: None)),
            path_qs=requested_path,
            route_url=pretend.call_recorder(lambda route, _query: "/manage/account/"),
            _=lambda x: x,
        )

        resp = forbidden(exc, request)

        assert resp.status_code == 303
        assert resp.location == "/manage/account/"
        assert request.session.flash.calls == [
            pretend.call(
                "You must verify your **primary** email address before you "
                "can perform this action.",
                queue="error",
            )
        ]

    def test_generic_warehousedeined(self, pyramid_config):
        result = WarehouseDenied(
            "This project requires two factor authentication to be enabled "
            "for all contributors.",
            reason="some_other_reason",
        )
        exc = pretend.stub(result=result)

        renderer = pyramid_config.testing_add_renderer("403.html")

        exc = pretend.stub(
            status_code=403, status="403 Forbidden", headers={}, result=result
        )
        request = pretend.stub(user=pretend.stub(), context=None)
        resp = forbidden(exc, request)
        assert resp.status_code == 403
        renderer.assert_()


class TestForbiddenIncludeView:
    def test_forbidden_include(self):
        exc = pretend.stub()
        request = pretend.stub()

        resp = forbidden_include(exc, request)

        assert resp.status_code == 403
        assert resp.content_type == "text/html"
        assert resp.content_length == 0


class TestForbiddenAPIView:
    def test_forbidden_api(self):
        exc = pretend.stub()
        request = pretend.stub()

        resp = forbidden_api(exc, request)

        assert resp.status_code == 403
        assert resp.content_type == "application/json"
        assert resp.json_body == {"message": "Access was denied to this resource."}


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
            filename=f"{project.name}-{release1.version}.tar.gz",
            python_version="source",
        )
        UserFactory.create()

        # Make sure that the task to update the database counts has been
        # called.
        compute_row_counts(db_request)

        assert index(db_request) == {
            "num_projects": 1,
            "num_users": 3,
            "num_releases": 2,
            "num_files": 1,
        }


class TestLocale:
    @pytest.mark.parametrize(
        ("referer", "redirect", "get", "valid"),
        [
            (None, "/fake-route", MultiDict({"locale_id": "en"}), True),
            (
                "/robots.txt",
                "/robots.txt",
                MultiDict({"locale_id": "non-existent-locale"}),
                False,
            ),
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

    @pytest.mark.parametrize(
        "get",
        [
            MultiDict({"nonsense": "arguments"}),
            MultiDict([("locale_id", "one"), ("locale_id", "two")]),
        ],
    )
    def test_locale_bad_request(self, get, monkeypatch):
        request = pretend.stub(
            GET=get,
            route_path=pretend.call_recorder(lambda r: "/fake-route"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            host=None,
        )

        with pytest.raises(HTTPBadRequest):
            locale(request)


def test_csi_current_user_indicator():
    assert current_user_indicator(pretend.stub()) == {}


def test_csi_flash_messages():
    assert flash_messages(pretend.stub()) == {}


def test_csi_session_notifications():
    assert session_notifications(pretend.stub()) == {}


def test_csi_sidebar_sponsor_logo():
    assert sidebar_sponsor_logo(pretend.stub()) == {}


class TestSearch:
    @pytest.mark.parametrize("page", [None, 1, 5])
    def test_with_a_query(self, monkeypatch, db_request, metrics, page):
        params = MultiDict({"q": "foo bar"})
        if page is not None:
            params["page"] = page
        db_request.params = params

        db_request.opensearch = pretend.stub()
        opensearch_query = pretend.stub()
        get_opensearch_query = pretend.call_recorder(lambda *a, **kw: opensearch_query)
        monkeypatch.setattr(views, "get_opensearch_query", get_opensearch_query)

        page_obj = pretend.stub(page_count=(page or 1) + 10, item_count=1000)
        page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
        monkeypatch.setattr(views, "OpenSearchPage", page_cls)

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
        assert get_opensearch_query.calls == [
            pretend.call(db_request.opensearch, params.get("q"), "", [])
        ]
        assert page_cls.calls == [
            pretend.call(opensearch_query, url_maker=url_maker, page=page or 1)
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

        opensearch_query = pretend.stub()
        db_request.opensearch = pretend.stub()
        get_opensearch_query = pretend.call_recorder(lambda *a, **kw: opensearch_query)
        monkeypatch.setattr(views, "get_opensearch_query", get_opensearch_query)

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
        monkeypatch.setattr(views, "OpenSearchPage", page_cls)

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
            pretend.call(opensearch_query, url_maker=url_maker, page=page or 1)
        ]
        assert url_maker_factory.calls == [pretend.call(db_request)]
        assert get_opensearch_query.calls == [
            pretend.call(db_request.opensearch, params.get("q"), "", params.getall("c"))
        ]
        assert metrics.histogram.calls == [
            pretend.call("warehouse.views.search.results", 1000)
        ]

    def test_returns_404_with_pagenum_too_high(self, monkeypatch, db_request, metrics):
        params = MultiDict({"page": 15})
        db_request.params = params

        opensearch_query = pretend.stub()
        db_request.opensearch = pretend.stub(query=lambda *a, **kw: opensearch_query)

        page_obj = pretend.stub(page_count=10, item_count=1000)
        page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
        monkeypatch.setattr(views, "OpenSearchPage", page_cls)

        url_maker = pretend.stub()
        url_maker_factory = pretend.call_recorder(lambda request: url_maker)
        monkeypatch.setattr(views, "paginate_url_factory", url_maker_factory)

        with pytest.raises(HTTPNotFound):
            search(db_request)

        assert page_cls.calls == [
            pretend.call(opensearch_query, url_maker=url_maker, page=15 or 1)
        ]
        assert url_maker_factory.calls == [pretend.call(db_request)]
        assert metrics.histogram.calls == []

    def test_raises_400_with_pagenum_type_str(self, monkeypatch, db_request, metrics):
        params = MultiDict({"page": "abc"})
        db_request.params = params

        opensearch_query = pretend.stub()
        db_request.opensearch = pretend.stub(query=lambda *a, **kw: opensearch_query)

        page_obj = pretend.stub(page_count=10, item_count=1000)
        page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
        monkeypatch.setattr(views, "OpenSearchPage", page_cls)

        url_maker = pretend.stub()
        url_maker_factory = pretend.call_recorder(lambda request: url_maker)
        monkeypatch.setattr(views, "paginate_url_factory", url_maker_factory)

        with pytest.raises(HTTPBadRequest):
            search(db_request)

        assert page_cls.calls == []
        assert metrics.histogram.calls == []

    def test_return_413_when_query_too_long(self, db_request, metrics):
        params = MultiDict({"q": "a" * 1001})
        db_request.params = params

        with pytest.raises(HTTPRequestEntityTooLarge):
            search(db_request)

        assert metrics.increment.calls == [
            pretend.call("warehouse.views.search.error", tags=["error:query_too_long"])
        ]

    def test_returns_503_when_opensearch_unavailable(
        self, monkeypatch, db_request, metrics
    ):
        params = MultiDict({"page": 15})
        db_request.params = params

        opensearch_query = pretend.stub()
        db_request.opensearch = pretend.stub(query=lambda *a, **kw: opensearch_query)

        def raiser(*args, **kwargs):
            raise opensearchpy.ConnectionError()

        monkeypatch.setattr(views, "OpenSearchPage", raiser)

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
        filename=f"{project.name}-{release1.version}.tar.gz",
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
    assert len(request.db.execute.calls) == 1
    assert len(request.db.execute.calls[0].args) == 1
    assert len(request.db.execute.calls[0].kwargs) == 0
    assert isinstance(
        request.db.execute.calls[0].args[0], sqlalchemy.sql.expression.TextClause
    )
    assert request.db.execute.calls[0].args[0].text == "SELECT 1"


class TestForceStatus:
    def test_valid(self):
        with pytest.raises(HTTPBadRequest):
            force_status(pretend.stub(matchdict={"status": "400"}))

    def test_invalid(self):
        with pytest.raises(HTTPNotFound):
            force_status(pretend.stub(matchdict={"status": "599"}))


class TestSecurityKeyGiveaway:
    def test_default_response(self):
        assert SecurityKeyGiveaway(pretend.stub()).default_response == {}

    def test_security_key_giveaway(self):
        request = pretend.stub()
        view = SecurityKeyGiveaway(request)

        assert view.security_key_giveaway() == view.default_response
