# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from pyramid.httpexceptions import HTTPMethodNotAllowed
from pyramid.viewderivers import INGRESS, csrf_view

from warehouse import csrf


class TestRequireMethodView:
    def test_passes_through_on_falsey(self):
        view = pretend.stub()
        info = pretend.stub(options={"require_methods": False})

        assert csrf.require_method_view(view, info) is view

    @pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
    def test_allows_safe_by_default(self, method):
        response = pretend.stub()

        @pretend.call_recorder
        def view(context, request):
            return response

        info = pretend.stub(options={})
        wrapped_view = csrf.require_method_view(view, info)

        context = pretend.stub()
        request = pretend.stub(method=method)

        assert wrapped_view(context, request) is response
        assert view.calls == [pretend.call(context, request)]

    @pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
    def test_disallows_unsafe_by_default(self, method):
        @pretend.call_recorder
        def view(context, request):
            pass

        info = pretend.stub(options={})
        wrapped_view = csrf.require_method_view(view, info)

        context = pretend.stub()
        request = pretend.stub(method=method)

        with pytest.raises(HTTPMethodNotAllowed):
            wrapped_view(context, request)

        assert view.calls == []

    def test_allows_passing_other_methods(self):
        response = pretend.stub()

        @pretend.call_recorder
        def view(context, request):
            return response

        info = pretend.stub(options={"require_methods": ["POST"]})
        wrapped_view = csrf.require_method_view(view, info)

        context = pretend.stub()
        request = pretend.stub(method="POST")

        assert wrapped_view(context, request) is response
        assert view.calls == [pretend.call(context, request)]

    def test_allows_exception_views_by_default(self):
        response = pretend.stub()

        @pretend.call_recorder
        def view(context, request):
            return response

        info = pretend.stub(options={})
        wrapped_view = csrf.require_method_view(view, info)

        context = pretend.stub()
        request = pretend.stub(method="POST", exception=pretend.stub())

        assert wrapped_view(context, request) is response
        assert view.calls == [pretend.call(context, request)]

    def test_explicit_controls_exception_views(self):
        @pretend.call_recorder
        def view(context, request):
            pass

        info = pretend.stub(options={"require_methods": ["POST"]})
        wrapped_view = csrf.require_method_view(view, info)

        context = pretend.stub()
        request = pretend.stub(method="GET")

        with pytest.raises(HTTPMethodNotAllowed):
            wrapped_view(context, request)

        assert view.calls == []


def test_includeme():
    config = pretend.stub(
        set_default_csrf_options=pretend.call_recorder(lambda **kw: None),
        add_view_deriver=pretend.call_recorder(lambda *args, **kw: None),
    )

    csrf.includeme(config)

    assert config.set_default_csrf_options.calls == [pretend.call(require_csrf=True)]
    assert config.add_view_deriver.calls == [
        pretend.call(csrf_view, under=INGRESS, over="secured_view"),
        pretend.call(csrf.require_method_view, under=INGRESS, over="csrf_view"),
    ]
