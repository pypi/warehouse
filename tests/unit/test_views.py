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
import uuid

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
from warehouse.accounts.forms import TitanPromoCodeForm
from warehouse.accounts.models import TitanPromoCode
from warehouse.errors import WarehouseDenied
from warehouse.views import (
    REDIRECT_FIELD_NAME,
    SecurityKeyGiveaway,
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
    sidebar_sponsor_logo,
    stats,
)

from ..common.db.accounts import UserFactory
from ..common.db.classifiers import ClassifierFactory
from ..common.db.packaging import (
    FileFactory,
    ProjectFactory,
    ReleaseFactory,
    RoleFactory,
)


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

    def test_json_404(self):
        csp = {}
        services = {"csp": pretend.stub(merge=csp.update)}
        context = HTTPNotFound()
        for path in (
            "/pypi/not_found_package/json",
            "/pypi/not_found_package/1.0.0/json",
        ):
            request = pretend.stub(find_service=lambda name: services[name], path=path)
            response = httpexception_view(context, request)
            assert response.status_code == 404
            assert response.status == "404 Not Found"
            assert response.content_type == "application/json"
            assert response.text == '{"message": "Not Found"}'


class TestForbiddenView:
    def test_logged_in_returns_exception(self, pyramid_config):
        renderer = pyramid_config.testing_add_renderer("403.html")

        exc = pretend.stub(
            status_code=403, status="403 Forbidden", headers={}, result=pretend.stub()
        )
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

    @pytest.mark.parametrize("reason", ("owners_require_2fa", "pypi_mandates_2fa"))
    def test_two_factor_required(self, reason):
        result = WarehouseDenied("Some summary", reason=reason)
        exc = pretend.stub(result=result)
        request = pretend.stub(
            authenticated_userid=1,
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
        request = pretend.stub(authenticated_userid=1)
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


class TestSecurityKeyGiveaway:
    def test_form(self):
        country = "United States"
        request = pretend.stub(POST={"country": country})
        form = SecurityKeyGiveaway(request).form

        assert isinstance(form, TitanPromoCodeForm)
        assert form.country.data == country

    def test_codes_available_no_codes(self, db_request):
        assert SecurityKeyGiveaway(db_request).codes_available is False

    def test_codes_available_no_unused_codes(self, db_request):
        db_request.db.add(TitanPromoCode(code="foo", user_id=str(uuid.uuid4())))

        assert SecurityKeyGiveaway(db_request).codes_available is False

    def test_codes_available(self, db_request):
        db_request.db.add(TitanPromoCode(code="foo"))

        assert SecurityKeyGiveaway(db_request).codes_available is True

    def test_eligible_projects_no_user(self, db_request):
        db_request.user = None

        assert SecurityKeyGiveaway(db_request).eligible_projects == set()

    def test_eligible_projects_owners_require_2fa(self, db_request):
        db_request.user = UserFactory.create()
        ProjectFactory.create()
        project = ProjectFactory.create(owners_require_2fa=True)
        RoleFactory.create(user=db_request.user, project=project)

        assert SecurityKeyGiveaway(db_request).eligible_projects == {project.name}

    def test_eligible_projects_pypi_mandates_2fa(self, db_request):
        db_request.user = UserFactory.create()
        ProjectFactory.create()
        project = ProjectFactory.create(pypi_mandates_2fa=True)
        RoleFactory.create(user=db_request.user, project=project)

        assert SecurityKeyGiveaway(db_request).eligible_projects == {project.name}

    def test_promo_code_no_user(self, db_request):
        db_request.user = None
        assert SecurityKeyGiveaway(db_request).promo_code is None

    def test_promo_code_no_codes(self, db_request):
        db_request.user = UserFactory.create()
        assert SecurityKeyGiveaway(db_request).promo_code is None

    def test_promo_code(self, db_request):
        db_request.user = UserFactory.create()
        code = TitanPromoCode(code="foo", user_id=db_request.user.id)
        db_request.db.add(code)
        assert SecurityKeyGiveaway(db_request).promo_code == code

    @pytest.mark.parametrize(
        "codes_available, eligible_projects, promo_code, user, eligible, reason_ineligible",  # noqa
        [
            (True, {"foo"}, None, False, True, None),
            (
                False,
                {"foo"},
                None,
                pretend.stub(has_two_factor=False),
                False,
                "At this time there are no keys available",
            ),
            (
                True,
                set(),
                None,
                pretend.stub(has_two_factor=False),
                False,
                "You are not a collaborator on any critical projects",
            ),
            (
                True,
                {"foo"},
                None,
                pretend.stub(has_two_factor=True),
                False,
                "You already have two-factor authentication enabled",
            ),
            (
                True,
                {"foo"},
                pretend.stub(),
                pretend.stub(has_two_factor=False),
                False,
                "Promo code has already been generated",
            ),
            (
                True,
                set(),
                None,
                None,
                False,
                "You are not a collaborator on any critical projects",
            ),
        ],
    )
    def test_default_response(
        self,
        codes_available,
        eligible_projects,
        promo_code,
        user,
        eligible,
        reason_ineligible,
        monkeypatch,
    ):
        request = pretend.stub(user=user)
        SecurityKeyGiveaway.codes_available = property(lambda a: codes_available)
        SecurityKeyGiveaway.eligible_projects = property(lambda a: eligible_projects)
        SecurityKeyGiveaway.promo_code = property(lambda a: promo_code)
        form = pretend.stub()
        SecurityKeyGiveaway.form = property(lambda a: form)
        ins = SecurityKeyGiveaway(request)

        assert ins.default_response == {
            "eligible": eligible,
            "reason_ineligible": reason_ineligible,
            "form": ins.form,
            "codes_available": codes_available,
            "eligible_projects": eligible_projects,
            "promo_code": promo_code,
            "REDIRECT_FIELD_NAME": REDIRECT_FIELD_NAME,
        }

    def test_security_key_giveaway_not_found(self):
        request = pretend.stub(registry=pretend.stub(settings={}))

        with pytest.raises(HTTPNotFound):
            SecurityKeyGiveaway(request).security_key_giveaway()

    def test_security_key_giveaway(self):
        request = pretend.stub(
            registry=pretend.stub(
                settings={"warehouse.two_factor_mandate.available": True}
            )
        )
        default_response = pretend.stub()
        SecurityKeyGiveaway.default_response = default_response

        assert SecurityKeyGiveaway(request).security_key_giveaway() == default_response

    def test_security_key_giveaway_submit_not_found(self):
        request = pretend.stub(registry=pretend.stub(settings={}))

        with pytest.raises(HTTPNotFound):
            SecurityKeyGiveaway(request).security_key_giveaway_submit()

    def test_security_key_giveaway_submit_invalid_form(self):
        request = pretend.stub(
            registry=pretend.stub(
                settings={"warehouse.two_factor_mandate.available": True}
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda a: None)),
        )
        default_response = pretend.stub()
        SecurityKeyGiveaway.default_response = default_response
        form = pretend.stub(validate=lambda: False)
        SecurityKeyGiveaway.form = property(lambda a: form)

        assert (
            SecurityKeyGiveaway(request).security_key_giveaway_submit()
            == default_response
        )
        assert request.session.flash.calls == [pretend.call("Form is not valid")]

    def test_security_key_giveaway_submit_ineligible(self):
        request = pretend.stub(
            registry=pretend.stub(
                settings={"warehouse.two_factor_mandate.available": True}
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda a: None)),
        )
        reason_ineligible = pretend.stub()
        default_response = {"eligible": False, "reason_ineligible": reason_ineligible}
        SecurityKeyGiveaway.default_response = default_response
        form = pretend.stub(validate=lambda: True)
        SecurityKeyGiveaway.form = property(lambda a: form)

        assert (
            SecurityKeyGiveaway(request).security_key_giveaway_submit()
            == default_response
        )
        assert request.session.flash.calls == [pretend.call(reason_ineligible)]

    def test_security_key_giveaway_submit(self, db_request):
        db_request.registry = pretend.stub(
            settings={"warehouse.two_factor_mandate.available": True}
        )
        db_request.session = pretend.stub(flash=pretend.call_recorder(lambda a: None))
        db_request.user = UserFactory.create()
        promo_code = TitanPromoCode(code="foo")
        db_request.db.add(promo_code)

        default_response = {"eligible": True}
        SecurityKeyGiveaway.default_response = default_response
        form = pretend.stub(validate=lambda: True)
        SecurityKeyGiveaway.form = property(lambda a: form)

        assert (
            SecurityKeyGiveaway(db_request).security_key_giveaway_submit()
            == default_response
        )
