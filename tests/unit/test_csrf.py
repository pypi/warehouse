# SPDX-License-Identifier: Apache-2.0

import types

import pytest

from pyramid.httpexceptions import HTTPMethodNotAllowed
from pyramid.viewderivers import INGRESS, csrf_view

from warehouse import csrf


class TestRequireMethodView:
    def test_passes_through_on_falsey(self, mocker):
        view = mocker.sentinel.view
        info = types.SimpleNamespace(options={"require_methods": False})

        assert csrf.require_method_view(view, info) is view

    @pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
    def test_allows_safe_by_default(self, method, mocker, pyramid_request):
        response = mocker.sentinel.response
        view = mocker.Mock(return_value=response)

        info = types.SimpleNamespace(options={})
        wrapped_view = csrf.require_method_view(view, info)

        context = mocker.sentinel.context
        pyramid_request.method = method

        assert wrapped_view(context, pyramid_request) is response
        view.assert_called_once_with(context, pyramid_request)

    @pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
    def test_disallows_unsafe_by_default(self, method, mocker, pyramid_request):
        view = mocker.Mock()

        info = types.SimpleNamespace(options={})
        wrapped_view = csrf.require_method_view(view, info)

        context = mocker.sentinel.context
        pyramid_request.method = method

        with pytest.raises(HTTPMethodNotAllowed):
            wrapped_view(context, pyramid_request)

        view.assert_not_called()

    def test_allows_passing_other_methods(self, mocker, pyramid_request):
        response = mocker.sentinel.response
        view = mocker.Mock(return_value=response)

        info = types.SimpleNamespace(options={"require_methods": ["POST"]})
        wrapped_view = csrf.require_method_view(view, info)

        context = mocker.sentinel.context
        pyramid_request.method = "POST"

        assert wrapped_view(context, pyramid_request) is response
        view.assert_called_once_with(context, pyramid_request)

    def test_allows_exception_views_by_default(self, mocker, pyramid_request):
        response = mocker.sentinel.response
        view = mocker.Mock(return_value=response)

        info = types.SimpleNamespace(options={})
        wrapped_view = csrf.require_method_view(view, info)

        context = mocker.sentinel.context
        pyramid_request.method = "POST"
        pyramid_request.exception = mocker.sentinel.exception

        assert wrapped_view(context, pyramid_request) is response
        view.assert_called_once_with(context, pyramid_request)

    def test_explicit_controls_exception_views(self, mocker, pyramid_request):
        view = mocker.Mock()

        info = types.SimpleNamespace(options={"require_methods": ["POST"]})
        wrapped_view = csrf.require_method_view(view, info)

        context = mocker.sentinel.context
        pyramid_request.method = "GET"

        with pytest.raises(HTTPMethodNotAllowed):
            wrapped_view(context, pyramid_request)

        view.assert_not_called()


def test_includeme(mocker):
    config = mocker.Mock(spec=["set_default_csrf_options", "add_view_deriver"])

    csrf.includeme(config)

    config.set_default_csrf_options.assert_called_once_with(require_csrf=True)
    assert config.add_view_deriver.call_args_list == [
        mocker.call(csrf_view, under=INGRESS, over="secured_view"),
        mocker.call(csrf.require_method_view, under=INGRESS, over="csrf_view"),
    ]
