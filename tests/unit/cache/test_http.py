# SPDX-License-Identifier: Apache-2.0

import types

import pytest

from warehouse.cache.http import (
    add_vary,
    cache_control,
    conditional_http_tween_factory,
    includeme,
)


@pytest.mark.parametrize("vary", [None, [], ["wat"]])
def test_add_vary(vary, mocker):
    response = types.SimpleNamespace(vary=vary)
    context = mocker.sentinel.context

    class FakeRequest:
        def __init__(self):
            self.callbacks = []

        def add_response_callback(self, callback):
            self.callbacks.append(callback)

    request = FakeRequest()

    def view(context, request):
        return response

    assert add_vary("foobar")(view)(context, request) is response
    assert len(request.callbacks) == 1

    request.callbacks[0](request, response)

    if vary is None:
        vary = []

    assert response.vary == {"foobar"} | set(vary)


class TestCacheControl:
    def test_cache_public(self, pyramid_request, mocker):
        response_obj = types.SimpleNamespace(
            cache_control=types.SimpleNamespace(public=None, max_age=None)
        )
        context_obj = mocker.sentinel.context

        @cache_control(12)
        def view(context, request):
            assert context is context_obj
            assert request is pyramid_request
            return response_obj

        response = view(context_obj, pyramid_request)

        assert response is response_obj
        assert response.cache_control.public
        assert response.cache_control.max_age == 12

    def test_cache_private(self, pyramid_request, mocker):
        response_obj = types.SimpleNamespace(
            cache_control=types.SimpleNamespace(private=None, max_age=None)
        )
        context_obj = mocker.sentinel.context

        @cache_control(12, public=False)
        def view(context, request):
            assert context is context_obj
            assert request is pyramid_request
            return response_obj

        response = view(context_obj, pyramid_request)

        assert response is response_obj
        assert response.cache_control.private
        assert response.cache_control.max_age == 12

    def test_no_cache(self, pyramid_request, mocker):
        response_obj = types.SimpleNamespace(
            cache_control=types.SimpleNamespace(
                no_cache=None, no_store=None, must_revalidate=None
            )
        )
        context_obj = mocker.sentinel.context

        @cache_control(False)
        def view(context, request):
            assert context is context_obj
            assert request is pyramid_request
            return response_obj

        response = view(context_obj, pyramid_request)

        assert response is response_obj
        assert response.cache_control.no_cache
        assert response.cache_control.no_store
        assert response.cache_control.must_revalidate

    def test_bypass_cache(self, pyramid_request, mocker):
        response_obj = mocker.sentinel.response
        pyramid_request.registry.settings["pyramid.prevent_http_cache"] = True
        context_obj = mocker.sentinel.context

        @cache_control(12)
        def view(context, request):
            assert context is context_obj
            assert request is pyramid_request
            return response_obj

        response = view(context_obj, pyramid_request)

        assert response is response_obj


class TestConditionalHTTPTween:
    def test_has_last_modified(self, pyramid_request, mocker):
        response = types.SimpleNamespace(
            last_modified=mocker.sentinel.last_modified,
            status_code=200,
            etag=None,
            conditional_response=False,
            app_iter=iter([b"foo"]),
            content_length=None,
        )
        handler = mocker.Mock(return_value=response)
        pyramid_request.method = "GET"

        tween = conditional_http_tween_factory(handler, mocker.sentinel.registry)

        assert tween(pyramid_request) is response
        handler.assert_called_once_with(pyramid_request)
        assert response.conditional_response

    def test_explicit_etag(self, pyramid_request, mocker):
        response = types.SimpleNamespace(
            last_modified=None,
            etag="foo",
            conditional_response=False,
            app_iter=iter([b"foo"]),
        )
        handler = mocker.Mock(return_value=response)

        tween = conditional_http_tween_factory(handler, mocker.sentinel.registry)

        assert tween(pyramid_request) is response
        handler.assert_called_once_with(pyramid_request)
        assert response.conditional_response

    @pytest.mark.parametrize("method", ["GET", "HEAD"])
    def test_implicit_etag(self, method, pyramid_request, mocker):
        response = types.SimpleNamespace(
            last_modified=None,
            etag=None,
            conditional_response=False,
            md5_etag=mocker.Mock(),
            app_iter=[b"foo"],
            status_code=200,
        )
        handler = mocker.Mock(return_value=response)
        pyramid_request.method = method

        tween = conditional_http_tween_factory(handler, mocker.sentinel.registry)

        assert tween(pyramid_request) is response
        handler.assert_called_once_with(pyramid_request)
        assert response.conditional_response
        response.md5_etag.assert_called_once_with()

    @pytest.mark.parametrize("method", ["GET", "HEAD"])
    def test_implicit_etag_buffers_streaming(self, method, pyramid_request, mocker):
        response = types.SimpleNamespace(
            last_modified=None,
            etag=None,
            conditional_response=False,
            md5_etag=mocker.Mock(),
            app_iter=iter([b"foo"]),
            body=b"foo",
            content_length=3,
            status_code=200,
        )
        handler = mocker.Mock(return_value=response)
        pyramid_request.method = method

        tween = conditional_http_tween_factory(handler, mocker.sentinel.registry)

        assert tween(pyramid_request) is response
        handler.assert_called_once_with(pyramid_request)
        assert response.conditional_response
        response.md5_etag.assert_called_once_with()

    @pytest.mark.parametrize("method", ["GET", "HEAD"])
    def test_no_implicit_etag_no_200(self, method, pyramid_request, mocker):
        response = types.SimpleNamespace(
            last_modified=None,
            etag=None,
            conditional_response=False,
            md5_etag=mocker.Mock(),
            app_iter=[b"foo"],
            status_code=201,
        )
        handler = mocker.Mock(return_value=response)
        pyramid_request.method = method

        tween = conditional_http_tween_factory(handler, mocker.sentinel.registry)

        assert tween(pyramid_request) is response
        handler.assert_called_once_with(pyramid_request)
        assert not response.conditional_response
        response.md5_etag.assert_not_called()

    @pytest.mark.parametrize("method", ["POST", "PUT"])
    def test_no_implicit_etag_wrong_method(self, method, pyramid_request, mocker):
        response = types.SimpleNamespace(
            last_modified=None,
            etag=None,
            conditional_response=False,
            md5_etag=mocker.Mock(),
            app_iter=[b"foo"],
            status_code=200,
        )
        handler = mocker.Mock(return_value=response)
        pyramid_request.method = method

        tween = conditional_http_tween_factory(handler, mocker.sentinel.registry)

        assert tween(pyramid_request) is response
        handler.assert_called_once_with(pyramid_request)
        assert not response.conditional_response
        response.md5_etag.assert_not_called()

    def test_no_etag(self, pyramid_request, mocker):
        response = types.SimpleNamespace(
            status_code=200,
            last_modified=None,
            etag=None,
            conditional_response=False,
            app_iter=iter([b"foo"]),
            content_length=None,
        )
        handler = mocker.Mock(return_value=response)
        pyramid_request.method = "GET"

        tween = conditional_http_tween_factory(handler, mocker.sentinel.registry)

        assert tween(pyramid_request) is response
        handler.assert_called_once_with(pyramid_request)
        assert not response.conditional_response


def test_includeme(mocker):
    config = mocker.Mock(spec=["add_tween"])
    includeme(config)

    config.add_tween.assert_called_once_with(
        "warehouse.cache.http.conditional_http_tween_factory"
    )
