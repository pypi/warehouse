# SPDX-License-Identifier: Apache-2.0

import datetime as dt

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import opensearchpy
import pytest

from paginate import Page
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPClientError,
    HTTPForbidden,
    HTTPNotFound,
    HTTPRequestEntityTooLarge,
    HTTPSeeOther,
    HTTPServiceUnavailable,
    HTTPTooManyRequests,
    exception_response,
)
from pyramid.i18n import Localizer
from pyramid.interfaces import ITranslationDirectories
from pyramid.response import FileResponse
from trove_classifiers import sorted_classifiers
from webob.multidict import MultiDict

from warehouse import views
from warehouse.csp import CSPPolicy
from warehouse.db import DatabaseNotAvailableError
from warehouse.errors import WarehouseDenied
from warehouse.packaging.models import ProjectFactory as DBProjectFactory
from warehouse.rate_limiting import DummyRateLimiter, RateLimiter
from warehouse.rate_limiting.interfaces import IRateLimiter, WindowStats
from warehouse.utils.row_counter import compute_row_counts
from warehouse.views import (
    SecurityKeyGiveaway,
    current_user_indicator,
    flash_messages,
    forbidden,
    forbidden_api,
    forbidden_include,
    force_status,
    funding_manifest_urls,
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


def _assert_has_cors_headers(headers):
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert headers["Access-Control-Allow-Headers"] == (
        "Content-Type, If-Match, If-Modified-Since, If-None-Match, If-Unmodified-Since"
    )
    assert headers["Access-Control-Allow-Methods"] == "GET"
    assert headers["Access-Control-Max-Age"] == "86400"
    assert headers["Access-Control-Expose-Headers"] == "X-PyPI-Last-Serial"


@pytest.fixture
def csp(pyramid_services):
    policy = CSPPolicy({})
    pyramid_services.register_service(policy, name="csp")
    return policy


class TestHTTPExceptionView:
    def test_returns_context_when_no_template(self, pyramid_config, pyramid_request):
        pyramid_config.testing_add_renderer("non-existent.html")

        context = HTTPClientError()
        context.status = "499 Client Closed Request"
        assert httpexception_view(context, pyramid_request) is context

    @pytest.mark.parametrize("status_code", [403, 404, 410, 500])
    def test_renders_template(self, pyramid_config, pyramid_request, csp, status_code):
        renderer = pyramid_config.testing_add_renderer(f"{status_code}.html")

        context = exception_response(status_code)
        context.status = f"{status_code} My Cool Status"
        response = httpexception_view(context, pyramid_request)

        assert response.status_code == status_code
        assert response.status == f"{status_code} My Cool Status"
        _assert_has_cors_headers(response.headers)
        renderer.assert_(project_name=None)

    @pytest.mark.parametrize("status_code", [403, 404, 410, 500])
    def test_renders_template_with_headers(
        self, pyramid_config, pyramid_request, csp, status_code
    ):
        renderer = pyramid_config.testing_add_renderer(f"{status_code}.html")

        context = exception_response(status_code, headers={"Foo": "Bar"})
        context.status = f"{status_code} My Cool Status"
        response = httpexception_view(context, pyramid_request)

        assert response.status_code == status_code
        assert response.status == f"{status_code} My Cool Status"
        assert response.headers["Foo"] == "Bar"
        _assert_has_cors_headers(response.headers)
        renderer.assert_(project_name=None)

    def test_renders_404_with_csp(self, pyramid_config, pyramid_request, csp):
        renderer = pyramid_config.testing_add_renderer("404.html")

        context = HTTPNotFound()
        response = httpexception_view(context, pyramid_request)

        assert response.status_code == 404
        assert response.status == "404 Not Found"
        assert csp == {
            "frame-src": ["https://www.youtube-nocookie.com"],
            "script-src": ["https://www.youtube.com", "https://s.ytimg.com"],
        }
        _assert_has_cors_headers(response.headers)
        renderer.assert_(project_name=None)

    @pytest.mark.parametrize(
        "path", ["/simple/not_found_package", "/simple/some/unusual/path/"]
    )
    def test_simple_404(self, pyramid_request, csp, path):
        context = HTTPNotFound()
        pyramid_request.path = path
        response = httpexception_view(context, pyramid_request)
        assert response.status_code == 404
        assert response.status == "404 Not Found"
        assert response.content_type == "text/plain"
        assert response.text == "404 Not Found"
        _assert_has_cors_headers(response.headers)

    @pytest.mark.parametrize(
        "path", ["/pypi/not_found_package/json", "/pypi/not_found_package/1.0.0/json"]
    )
    def test_json_404(self, pyramid_request, csp, path):
        context = HTTPNotFound()
        pyramid_request.path = path
        response = httpexception_view(context, pyramid_request)
        assert response.status_code == 404
        assert response.status == "404 Not Found"
        assert response.content_type == "application/json"
        assert response.text == '{"message": "Not Found"}'
        _assert_has_cors_headers(response.headers)

    def test_context_is_project(self, pyramid_config, pyramid_request, csp):
        renderer = pyramid_config.testing_add_renderer("404.html")

        context = HTTPNotFound()
        project = ProjectFactory.create()
        pyramid_request.context = project
        response = httpexception_view(context, pyramid_request)

        assert response.status_code == 404
        renderer.assert_(project_name=project.name)

    def test_context_is_projectfactory(self, pyramid_config, pyramid_request, csp):
        renderer = pyramid_config.testing_add_renderer("404.html")

        context = HTTPNotFound()
        pyramid_request.matchdict = {"name": "missing-project"}
        pyramid_request.context = DBProjectFactory(pyramid_request)
        response = httpexception_view(context, pyramid_request)

        assert response.status_code == 404
        renderer.assert_(project_name="missing-project")


class TestForbiddenView:
    def test_logged_in_returns_exception(
        self, mocker, pyramid_config, pyramid_request, pyramid_user
    ):
        renderer = pyramid_config.testing_add_renderer("403.html")

        exc = HTTPForbidden(result=mocker.sentinel.result)
        resp = forbidden(exc, pyramid_request)
        assert resp.status_code == 403
        renderer.assert_(project_name=None)

    def test_logged_out_redirects_login(self, pyramid_config, pyramid_request):
        pyramid_config.add_route("accounts.login", "/account/login/")
        pyramid_request.path_qs = "/foo/bar/?b=s"

        resp = forbidden(HTTPForbidden(), pyramid_request)

        assert resp.status_code == 303
        location = urlsplit(resp.headers["Location"])
        assert location.path == "/account/login/"
        assert parse_qs(location.query) == {"next": ["/foo/bar/?b=s"]}

    @pytest.mark.parametrize("reason", ["manage_2fa_required"])
    def test_two_factor_required(
        self, mocker, pyramid_config, pyramid_request, pyramid_user, reason
    ):
        pyramid_config.add_route(
            "manage.account.two-factor", "/manage/account/two-factor/"
        )
        flash = mocker.spy(pyramid_request.session, "flash")
        result = WarehouseDenied("Some summary", reason=reason)
        pyramid_request.path_qs = "/foo/bar/?b=s"

        resp = forbidden(HTTPForbidden(result=result), pyramid_request)

        assert resp.status_code == 303
        location = urlsplit(resp.headers["Location"])
        assert location.path == "/manage/account/two-factor/"
        assert parse_qs(location.query) == {"next": ["/foo/bar/?b=s"]}
        flash.assert_called_once_with(
            "Two-factor authentication must be enabled on your account to "
            "perform this action.",
            queue="error",
        )

    @pytest.mark.parametrize(
        "requested_path",
        ["/manage/projects/", "/manage/account/two-factor/", "/manage/organizations/"],
    )
    def test_unverified_email_redirects(
        self, mocker, pyramid_config, pyramid_request, pyramid_user, requested_path
    ):
        pyramid_config.add_route(
            "manage.unverified-account", "/manage/unverified-account/"
        )
        flash = mocker.spy(pyramid_request.session, "flash")
        result = WarehouseDenied("Some summary", reason="unverified_email")
        pyramid_request.path_qs = requested_path

        resp = forbidden(HTTPForbidden(result=result), pyramid_request)

        assert resp.status_code == 303
        location = urlsplit(resp.location)
        assert location.path == "/manage/unverified-account/"
        assert parse_qs(location.query) == {"next": [requested_path]}
        flash.assert_called_once_with(
            "You must verify your **primary** email address before you "
            "can perform this action.",
            queue="error",
        )

    def test_generic_warehousedeined(
        self, pyramid_config, pyramid_request, pyramid_user
    ):
        result = WarehouseDenied(
            "This project requires two factor authentication to be enabled "
            "for all contributors.",
            reason="some_other_reason",
        )

        renderer = pyramid_config.testing_add_renderer("403.html")

        exc = HTTPForbidden(result=result)
        resp = forbidden(exc, pyramid_request)
        assert resp.status_code == 403
        renderer.assert_(project_name=None)


class TestForbiddenIncludeView:
    def test_forbidden_include(self, mocker):
        resp = forbidden_include(mocker.sentinel.exc, mocker.sentinel.request)

        assert resp.status_code == 403
        assert resp.content_type == "text/html"
        assert resp.content_length == 0


class TestForbiddenAPIView:
    def test_forbidden_api(self, mocker):
        resp = forbidden_api(mocker.sentinel.exc, mocker.sentinel.request)

        assert resp.status_code == 403
        assert resp.content_type == "application/json"
        assert resp.json_body == {"message": "Access was denied to this resource."}


class TestServiceUnavailableView:
    def test_renders_503(self, pyramid_config, pyramid_request):
        renderer = pyramid_config.testing_add_renderer("503.html")
        renderer.string_response = "A 503 Error"

        resp = service_unavailable(DatabaseNotAvailableError(), pyramid_request)

        assert resp.status_code == 503
        assert resp.content_type == "text/html"
        assert resp.body == b"A 503 Error"
        _assert_has_cors_headers(resp.headers)


def test_favicon(pyramid_config, pyramid_request):
    pyramid_config.add_static_view("static", "warehouse:static/dist/")
    # Construct the path to the favicon.ico file relative to the codebase directory
    codebase_dir = Path(__file__).resolve().parent.parent.parent
    favicon_path = (
        codebase_dir / "warehouse" / "static" / "dist" / "images" / "favicon.ico"
    )
    # Create a dummy file to test the favicon
    favicon_path.parent.mkdir(parents=True, exist_ok=True)
    favicon_path.touch()

    response = views.favicon(pyramid_request)

    assert isinstance(response, FileResponse)
    assert pyramid_request.response.content_type == "image/x-icon"
    response.app_iter.close()


def test_robotstxt(pyramid_request):
    assert robotstxt(pyramid_request) == {}
    assert pyramid_request.response.content_type == "text/plain"


def test_funding_manifest_urls(pyramid_request):
    response = funding_manifest_urls(pyramid_request)
    assert response.text == "https://www.python.org/funding.json"
    assert response.content_type == "text/plain"
    assert response.charset == "utf-8"


def test_opensearchxml(pyramid_request):
    assert opensearchxml(pyramid_request) == {}
    assert pyramid_request.response.content_type == "text/xml"


class TestIndex:
    def test_index(self, db_request):
        project = ProjectFactory.create()
        release1 = ReleaseFactory.create(project=project)
        release1.created = dt.date(2011, 1, 1)
        release2 = ReleaseFactory.create(project=project)
        release2.created = dt.date(2012, 1, 1)
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
            (None, "/", MultiDict({"locale_id": "en"}), True),
            (
                "/robots.txt",
                "/robots.txt",
                MultiDict({"locale_id": "non-existent-locale"}),
                False,
            ),
        ],
    )
    def test_locale(
        self, mocker, pyramid_config, pyramid_request, referer, redirect, get, valid
    ):
        localizer = mocker.create_autospec(Localizer, instance=True)
        localizer.translate.return_value = "translated"
        make_localizer = mocker.patch.object(
            views, "make_localizer", autospec=True, return_value=localizer
        )
        tdirs = mocker.sentinel.tdirs
        pyramid_config.registry.registerUtility(tdirs, ITranslationDirectories)
        pyramid_config.add_route("index", "/")
        flash = mocker.spy(pyramid_request.session, "flash")
        pyramid_request.GET = get
        pyramid_request.referer = referer

        result = locale(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == redirect

        if valid:
            assert "Set-Cookie" in result.headers
            assert f"_LOCALE_={get['locale_id']};" in result.headers["Set-Cookie"]
            make_localizer.assert_called_once_with(get["locale_id"], tdirs)
            flash.assert_called_once_with("translated", queue="success")
        else:
            assert "Set-Cookie" not in result.headers
            make_localizer.assert_not_called()
            flash.assert_not_called()

    @pytest.mark.parametrize(
        "get",
        [
            MultiDict({"nonsense": "arguments"}),
            MultiDict([("locale_id", "one"), ("locale_id", "two")]),
        ],
    )
    def test_locale_bad_request(self, pyramid_request, get):
        pyramid_request.GET = get

        with pytest.raises(HTTPBadRequest):
            locale(pyramid_request)


def test_csi_current_user_indicator(mocker):
    assert current_user_indicator(mocker.sentinel.request) == {}


def test_csi_flash_messages(mocker):
    assert flash_messages(mocker.sentinel.request) == {}


def test_csi_session_notifications(mocker):
    assert session_notifications(mocker.sentinel.request) == {}


def test_csi_sidebar_sponsor_logo(mocker):
    assert sidebar_sponsor_logo(mocker.sentinel.request) == {}


class TestSearch:
    @pytest.fixture
    def search_ratelimiter(self, mocker, pyramid_services):
        ratelimiter = DummyRateLimiter()
        mocker.spy(ratelimiter, "test")
        mocker.spy(ratelimiter, "hit")
        pyramid_services.register_service(
            ratelimiter, IRateLimiter, None, name="search"
        )
        return ratelimiter

    @pytest.fixture
    def get_opensearch_query(self, mocker, db_request):
        db_request.opensearch = mocker.sentinel.opensearch
        return mocker.patch.object(
            views,
            "get_opensearch_query",
            autospec=True,
            return_value=mocker.sentinel.opensearch_query,
        )

    @pytest.fixture
    def opensearch(self, mocker, db_request):
        db_request.opensearch = mocker.create_autospec(
            opensearchpy.Search, instance=True
        )
        db_request.opensearch.query.return_value = mocker.sentinel.opensearch_query
        return db_request.opensearch

    @pytest.fixture
    def url_maker_factory(self, mocker):
        return mocker.patch.object(
            views,
            "paginate_url_factory",
            autospec=True,
            return_value=mocker.sentinel.url_maker,
        )

    @pytest.mark.parametrize("page", [None, 1, 5])
    def test_with_a_query(
        self,
        mocker,
        search_ratelimiter,
        get_opensearch_query,
        url_maker_factory,
        db_request,
        metrics,
        page,
    ):
        params = MultiDict({"q": "foo bar"})
        if page is not None:
            params["page"] = str(page)
        db_request.params = params

        page_obj = Page([], item_count=1000, items_per_page=10)
        page_cls = mocker.patch.object(
            views, "OpenSearchPage", autospec=True, return_value=page_obj
        )

        result = search(db_request)
        assert result["page"] is page_obj
        assert result == {
            "page": page_obj,
            "term": params.get("q", ""),
            "order": "",
            "applied_filters": [],
            "available_filters": [],
        }
        get_opensearch_query.assert_called_once_with(
            mocker.sentinel.opensearch, params.get("q"), "", []
        )
        page_cls.assert_called_once_with(
            mocker.sentinel.opensearch_query,
            url_maker=mocker.sentinel.url_maker,
            page=page or 1,
        )
        url_maker_factory.assert_called_once_with(db_request)
        search_ratelimiter.hit.assert_called_once_with(db_request.remote_addr)
        search_ratelimiter.test.assert_called_once_with(db_request.remote_addr)
        metrics.histogram.assert_called_once_with(
            "warehouse.views.search.results", 1000
        )

    @pytest.mark.parametrize("page", [None, 1, 5])
    def test_with_classifiers(
        self,
        mocker,
        search_ratelimiter,
        get_opensearch_query,
        url_maker_factory,
        db_request,
        metrics,
        page,
    ):
        params = MultiDict([("q", "foo bar"), ("c", "foo :: bar"), ("c", "fiz :: buz")])
        if page is not None:
            params["page"] = str(page)
        db_request.params = params

        classifier1 = ClassifierFactory.create(classifier="foo :: bar")
        classifier2 = ClassifierFactory.create(classifier="foo :: baz")
        classifier3 = ClassifierFactory.create(classifier="fiz :: buz")

        project = ProjectFactory.create()
        release1 = ReleaseFactory.create(project=project)
        release1.created = dt.date(2011, 1, 1)
        release1._classifiers.append(classifier1)
        release1._classifiers.append(classifier2)

        page_obj = Page([], item_count=1000, items_per_page=10)
        page_cls = mocker.patch.object(
            views, "OpenSearchPage", autospec=True, return_value=page_obj
        )

        search_view = search(db_request)
        assert search_view["page"] is page_obj
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
        page_cls.assert_called_once_with(
            mocker.sentinel.opensearch_query,
            url_maker=mocker.sentinel.url_maker,
            page=page or 1,
        )

        url_maker_factory.assert_called_once_with(db_request)
        get_opensearch_query.assert_called_once_with(
            mocker.sentinel.opensearch, params.get("q"), "", params.getall("c")
        )
        metrics.histogram.assert_called_once_with(
            "warehouse.views.search.results", 1000
        )

    def test_returns_404_with_pagenum_too_high(
        self,
        mocker,
        search_ratelimiter,
        opensearch,
        url_maker_factory,
        db_request,
        metrics,
    ):
        params = MultiDict({"page": "15"})
        db_request.params = params

        page_obj = Page([], item_count=1000, items_per_page=100)
        page_cls = mocker.patch.object(
            views, "OpenSearchPage", autospec=True, return_value=page_obj
        )

        with pytest.raises(HTTPNotFound):
            search(db_request)

        page_cls.assert_called_once_with(
            mocker.sentinel.opensearch_query,
            url_maker=mocker.sentinel.url_maker,
            page=15,
        )
        url_maker_factory.assert_called_once_with(db_request)
        metrics.histogram.assert_not_called()

    def test_raises_400_with_pagenum_type_str(
        self, mocker, search_ratelimiter, opensearch, db_request, metrics
    ):
        params = MultiDict({"page": "abc"})
        db_request.params = params

        page_cls = mocker.patch.object(views, "OpenSearchPage", autospec=True)

        with pytest.raises(HTTPBadRequest):
            search(db_request)

        page_cls.assert_not_called()
        metrics.histogram.assert_not_called()

    def test_return_413_when_query_too_long(
        self, mocker, search_ratelimiter, db_request, metrics
    ):
        params = MultiDict({"q": "a" * 1001})
        db_request.params = params

        with pytest.raises(HTTPRequestEntityTooLarge):
            search(db_request)

        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.search.ratelimiter.hit"),
            mocker.call("warehouse.views.search.error", tags=["error:query_too_long"]),
        ]

    def test_returns_503_when_opensearch_unavailable(
        self,
        mocker,
        search_ratelimiter,
        opensearch,
        url_maker_factory,
        db_request,
        metrics,
    ):
        params = MultiDict({"page": "15"})
        db_request.params = params

        mocker.patch.object(
            views,
            "OpenSearchPage",
            autospec=True,
            side_effect=opensearchpy.ConnectionError,
        )

        with pytest.raises(HTTPServiceUnavailable):
            search(db_request)

        url_maker_factory.assert_called_once_with(db_request)
        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.search.ratelimiter.hit"),
            mocker.call("warehouse.views.search.error"),
        ]
        metrics.histogram.assert_not_called()

    @pytest.mark.parametrize("resets_in", [None, 1, 5])
    def test_returns_429_when_ratelimited(
        self, mocker, pyramid_services, db_request, metrics, resets_in
    ):
        params = MultiDict({"q": "foo bar"})
        db_request.params = params

        stats = [
            WindowStats(amount=5, window_seconds=1, remaining=0, resets_in_seconds=1)
        ]
        ratelimiter = mocker.create_autospec(RateLimiter, instance=True)
        ratelimiter.test.return_value = False
        ratelimiter.resets_in.return_value = (
            None if resets_in is None else dt.timedelta(seconds=resets_in)
        )
        ratelimiter.get_window_stats.return_value = stats
        pyramid_services.register_service(
            ratelimiter, IRateLimiter, None, name="search"
        )

        with pytest.raises(HTTPTooManyRequests) as exc_info:
            search(db_request)

        message = (
            "Your search query could not be performed because there were too "
            "many requests by the client."
        )
        if resets_in is not None:
            message += f" Limit may reset in {resets_in} seconds."

        assert exc_info.value.args[0] == message
        ratelimiter.hit.assert_called_once_with(db_request.remote_addr)
        ratelimiter.test.assert_called_once_with(db_request.remote_addr)
        metrics.increment.assert_called_once_with(
            "warehouse.search.ratelimiter.exceeded"
        )
        # Snapshot is recorded even on the blocked path so headers can be
        # emitted on the 429 response.
        snapshots = db_request._rate_limit_snapshots
        assert [s.name for s in snapshots] == ["search"]
        assert snapshots[0].partition_key == "ip"
        assert snapshots[0].stats is stats


def test_classifiers(db_request):
    assert list_classifiers(db_request) == {"classifiers": sorted_classifiers}


def test_stats(db_request):
    project = ProjectFactory.create()
    release1 = ReleaseFactory.create(project=project)
    release1.created = dt.date(2011, 1, 1)
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


def test_health(db_request, query_recorder):
    with query_recorder:
        assert health(db_request) == "OK"

    assert query_recorder.queries == ["SELECT 1"]


class TestForceStatus:
    def test_valid(self, pyramid_request):
        pyramid_request.matchdict = {"status": "400"}
        with pytest.raises(HTTPBadRequest):
            force_status(pyramid_request)

    def test_invalid(self, pyramid_request):
        pyramid_request.matchdict = {"status": "599"}
        with pytest.raises(HTTPNotFound):
            force_status(pyramid_request)


class TestSecurityKeyGiveaway:
    def test_default_response(self, mocker):
        assert SecurityKeyGiveaway(mocker.sentinel.request).default_response == {}

    def test_security_key_giveaway(self, mocker):
        view = SecurityKeyGiveaway(mocker.sentinel.request)

        assert view.security_key_giveaway() == view.default_response
