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

import itertools
import pretend
import pytest

from pyramid.config.views import DefaultViewMapper
from pyramid.httpexceptions import HTTPMethodNotAllowed
from pyramid.interfaces import IViewMapperFactory

from warehouse import csrf


class TestDecorators:

    def test_csrf_exempt(self):
        @pretend.call_recorder
        def view(context, request):
            pass

        context = pretend.stub()
        request = pretend.stub()

        wrapped = csrf.csrf_exempt(view)
        wrapped(context, request)

        assert view.calls == [pretend.call(context, request)]
        assert not request._process_csrf

    def test_unscoped_csrf_protect(self):
        @pretend.call_recorder
        def view(context, request):
            pass

        context = pretend.stub()
        request = pretend.stub()

        wrapped = csrf.csrf_protect(view)
        wrapped(context, request)

        assert view.calls == [pretend.call(context, request)]
        assert request._process_csrf
        assert request._csrf_scope is None

    def test_scoped_csrf_protect(self):
        @pretend.call_recorder
        def view(context, request):
            pass

        context = pretend.stub()
        request = pretend.stub()

        wrapped = csrf.csrf_protect("my scope")(view)
        wrapped(context, request)

        assert view.calls == [pretend.call(context, request)]
        assert request._process_csrf
        assert request._csrf_scope is "my scope"


class TestCheckCSRF:

    @pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "TRACE"])
    def test_safe_method(self, method):
        request = pretend.stub(method=method)
        csrf._check_csrf(request)

    @pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
    def test_unsafe_method_no_process(self, method):
        request = pretend.stub(method=method)
        with pytest.raises(HTTPMethodNotAllowed):
            csrf._check_csrf(request)

        request = pretend.stub(method=method)
        request._process_csrf = None
        with pytest.raises(HTTPMethodNotAllowed):
            csrf._check_csrf(request)

    @pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
    def test_unsafe_method_https_no_origin(self, method):
        request = pretend.stub(headers={}, method=method, scheme="https")
        request._process_csrf = True

        with pytest.raises(csrf.InvalidCSRF) as exc:
            csrf._check_csrf(request)

        assert exc.value.args[0] == csrf.REASON_NO_ORIGIN

    @pytest.mark.parametrize(
        ("method", "headers"),
        itertools.product(
            ["POST", "PUT", "DELETE"],
            [
                {"Origin": "null"},
                {"Origin": "https://o.example.com"},
                {"Referer": "https://r.example.com"},
                {
                    "Origin": "https://o.example.com",
                    "Referer": "https://r.example.com",
                },
            ],
        ),
    )
    def test_unsafe_method_https_origin_invalid(self, method, headers):
        request = pretend.stub(
            headers=headers,
            method=method,
            scheme="https",
            host_url="https://a.example.com/",
        )
        request._process_csrf = True

        with pytest.raises(csrf.InvalidCSRF) as exc:
            csrf._check_csrf(request)

        origin = request.headers.get("Origin", request.headers.get("Referer"))

        assert exc.value.args[0] == csrf.REASON_BAD_ORIGIN.format(
            origin,
            request.host_url,
        )

    @pytest.mark.parametrize(
        ("method", "headers", "post", "scheme", "scope"),
        itertools.product(
            ["POST", "PUT", "DELETE"],
            [
                {"Origin": "https://a.example.com"},
                {"Referer": "https://a.example.com"},
                {
                    "Origin": "https://a.example.com",
                    "Referer": "https://r.example.com",
                },
                {"Origin": "https://a.example.com", "CSRFToken": "wrong"},
                {"Referer": "https://a.example.com", "CSRFToken": "wrong"},
                {
                    "Origin": "https://a.example.com",
                    "Referer": "https://r.example.com",
                    "CSRFToken": "wrong",
                },
            ],
            [{}, {"csrf_token": "invalid"}],
            ["http", "https"],
            [None, "my scope"]
        ),
    )
    def test_unsafe_method_wrong_token(self, method, headers, post, scheme,
                                       scope):
        request = pretend.stub(
            headers=headers,
            method=method,
            scheme=scheme,
            host_url="https://a.example.com/",
            session=pretend.stub(
                get_scoped_csrf_token=pretend.call_recorder(
                    lambda scope: "123456"
                ),
                get_csrf_token=pretend.call_recorder(lambda: "123456"),
            ),
            POST=post,
        )
        request._process_csrf = True
        request._csrf_scope = scope

        with pytest.raises(csrf.InvalidCSRF) as exc:
            csrf._check_csrf(request)

        assert exc.value.args[0] == csrf.REASON_BAD_TOKEN

        if scope is not None:
            assert request.session.get_scoped_csrf_token.calls == [
                pretend.call(scope),
            ]
            assert request.session.get_csrf_token.calls == []
        else:
            assert request.session.get_csrf_token.calls == [pretend.call()]
            assert request.session.get_scoped_csrf_token.calls == []

    @pytest.mark.parametrize(
        ("method", "headers", "scheme", "scope"),
        itertools.product(
            ["POST", "PUT", "DELETE"],
            [
                {"Origin": "https://a.example.com"},
                {"Referer": "https://a.example.com"},
                {
                    "Origin": "https://a.example.com",
                    "Referer": "https://r.example.com",
                },
                {"Origin": "https://a.example.com", "CSRFToken": "wrong"},
                {"Referer": "https://a.example.com", "CSRFToken": "wrong"},
                {
                    "Origin": "https://a.example.com",
                    "Referer": "https://r.example.com",
                    "CSRFToken": "wrong",
                },
            ],
            ["http", "https"],
            [None, "my scope"]
        ),
    )
    def test_unsafe_method_via_post(self, method, headers, scheme, scope):
        request = pretend.stub(
            headers=headers,
            method=method,
            scheme=scheme,
            host_url="https://a.example.com/",
            session=pretend.stub(
                get_scoped_csrf_token=pretend.call_recorder(
                    lambda scope: "123456"
                ),
                get_csrf_token=pretend.call_recorder(lambda: "123456"),
            ),
            POST={"csrf_token": "123456"},
        )
        request._process_csrf = True
        request._csrf_scope = scope

        csrf._check_csrf(request)

        if scope is not None:
            assert request.session.get_scoped_csrf_token.calls == [
                pretend.call(scope),
            ]
            assert request.session.get_csrf_token.calls == []
        else:
            assert request.session.get_csrf_token.calls == [pretend.call()]
            assert request.session.get_scoped_csrf_token.calls == []

    @pytest.mark.parametrize(
        ("method", "headers", "scheme", "scope"),
        itertools.product(
            ["POST", "PUT", "DELETE"],
            [
                {"Origin": "https://a.example.com"},
                {"Referer": "https://a.example.com"},
                {
                    "Origin": "https://a.example.com",
                    "Referer": "https://r.example.com",
                },
                {"Origin": "https://a.example.com"},
                {"Referer": "https://a.example.com"},
                {
                    "Origin": "https://a.example.com",
                    "Referer": "https://r.example.com",
                },
            ],
            ["http", "https"],
            [None, "my scope"]
        ),
    )
    def test_unsafe_method_via_header(self, method, headers, scheme, scope):
        headers.update({"CSRFToken": "123456"})
        request = pretend.stub(
            headers=headers,
            method=method,
            scheme=scheme,
            host_url="https://a.example.com/",
            session=pretend.stub(
                get_scoped_csrf_token=pretend.call_recorder(
                    lambda scope: "123456"
                ),
                get_csrf_token=pretend.call_recorder(lambda: "123456"),
            ),
            POST={},
        )
        request._process_csrf = True
        request._csrf_scope = scope

        csrf._check_csrf(request)

        if scope is not None:
            assert request.session.get_scoped_csrf_token.calls == [
                pretend.call(scope),
            ]
            assert request.session.get_csrf_token.calls == []
        else:
            assert request.session.get_csrf_token.calls == [pretend.call()]
            assert request.session.get_scoped_csrf_token.calls == []


class TestCSRFMapperFactory:

    def test_exempt_view(self, monkeypatch):
        def raiser(*args, **kwargs):
            assert False, "This method should not be called"
        monkeypatch.setattr(csrf, "_check_csrf", raiser)

        class FakeMapper:
            def __call__(self, view):
                return view

        mapper = csrf.csrf_mapper_factory(FakeMapper)()

        @pretend.call_recorder
        def view(context, request):
            pass

        context = pretend.stub()
        request = pretend.stub(_process_csrf=False)

        wrapped = mapper(view)
        wrapped(context, request)

        assert view.calls == [pretend.call(context, request)]

    def test_non_csrf_view(self, monkeypatch):
        checker = pretend.call_recorder(lambda request: None)
        monkeypatch.setattr(csrf, "_check_csrf", checker)

        class FakeMapper:
            def __call__(self, view):
                return view

        mapper = csrf.csrf_mapper_factory(FakeMapper)()

        @pretend.call_recorder
        def view(context, request):
            pass

        context = pretend.stub()
        request = pretend.stub()

        wrapped = mapper(view)
        wrapped(context, request)

        assert checker.calls == [pretend.call(request)]
        assert view.calls == [pretend.call(context, request)]

    def test_csrf_protected_view(self, monkeypatch, pyramid_request):
        checker = pretend.call_recorder(lambda request: None)
        monkeypatch.setattr(csrf, "_check_csrf", checker)

        class FakeMapper:
            def __call__(self, view):
                return view

        mapper = csrf.csrf_mapper_factory(FakeMapper)()

        @pretend.call_recorder
        def view(context, request):
            pass

        context = pretend.stub()
        request = pyramid_request
        request._process_csrf = True

        wrapped = mapper(view)
        wrapped(context, request)

        assert checker.calls == [pretend.call(request)]
        assert view.calls == [pretend.call(context, request)]
        assert len(request.response_callbacks) == 1

        response = pretend.stub(vary=[])
        request.response_callbacks[0](request, response)
        assert response.vary == {"Cookie"}


@pytest.mark.parametrize("mapper", [None, True])
def test_includeme(mapper, monkeypatch):
    if mapper:
        class Mapper:
            pass

        mapper = Mapper

    mapper_cls = pretend.stub()
    csrf_mapper_factory = pretend.call_recorder(lambda m: mapper_cls)
    monkeypatch.setattr(csrf, "csrf_mapper_factory", csrf_mapper_factory)

    config = pretend.stub(
        commit=pretend.call_recorder(lambda: None),
        registry=pretend.stub(
            queryUtility=pretend.call_recorder(lambda x: mapper),
        ),
        set_view_mapper=pretend.call_recorder(lambda m: None)
    )

    csrf.includeme(config)

    assert config.commit.calls == [pretend.call()]
    assert config.registry.queryUtility.calls == [
        pretend.call(IViewMapperFactory),
    ]
    assert csrf_mapper_factory.calls == [
        pretend.call(mapper if mapper is not None else DefaultViewMapper),
    ]
    assert config.set_view_mapper.calls == [pretend.call(mapper_cls)]
