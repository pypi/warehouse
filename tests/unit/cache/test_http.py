# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from warehouse.cache.http import (
    add_vary,
    cache_control,
    conditional_http_tween_factory,
    includeme,
)


@pytest.mark.parametrize("vary", [None, [], ["wat"]])
def test_add_vary(vary):
    class FakeRequest:
        def __init__(self):
            self.callbacks = []

        def add_response_callback(self, callback):
            self.callbacks.append(callback)

    response = pretend.stub(vary=vary)
    context = pretend.stub()
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
    def test_cache_public(self):
        response_obj = pretend.stub(
            cache_control=pretend.stub(public=None, max_age=None)
        )
        request_obj = pretend.stub(registry=pretend.stub(settings={}))
        context_obj = pretend.stub()

        @cache_control(12)
        def view(context, request):
            assert context is context_obj
            assert request is request_obj
            return response_obj

        response = view(context_obj, request_obj)

        assert response is response_obj
        assert response.cache_control.public
        assert response.cache_control.max_age == 12

    def test_cache_private(self):
        response_obj = pretend.stub(
            cache_control=pretend.stub(private=None, max_age=None)
        )
        request_obj = pretend.stub(registry=pretend.stub(settings={}))
        context_obj = pretend.stub()

        @cache_control(12, public=False)
        def view(context, request):
            assert context is context_obj
            assert request is request_obj
            return response_obj

        response = view(context_obj, request_obj)

        assert response is response_obj
        assert response.cache_control.private
        assert response.cache_control.max_age == 12

    def test_no_cache(self):
        response_obj = pretend.stub(
            cache_control=pretend.stub(
                no_cache=None, no_store=None, must_revalidate=None
            )
        )
        request_obj = pretend.stub(registry=pretend.stub(settings={}))
        context_obj = pretend.stub()

        @cache_control(False)
        def view(context, request):
            assert context is context_obj
            assert request is request_obj
            return response_obj

        response = view(context_obj, request_obj)

        assert response is response_obj
        assert response.cache_control.no_cache
        assert response.cache_control.no_store
        assert response.cache_control.must_revalidate

    def test_bypass_cache(self):
        response_obj = pretend.stub()
        request_obj = pretend.stub(
            registry=pretend.stub(settings={"pyramid.prevent_http_cache": True})
        )
        context_obj = pretend.stub()

        @cache_control(12)
        def view(context, request):
            assert context is context_obj
            assert request is request_obj
            return response_obj

        response = view(context_obj, request_obj)

        assert response is response_obj


class TestConditionalHTTPTween:
    def test_has_last_modified(self):
        response = pretend.stub(
            last_modified=pretend.stub(),
            status_code=200,
            etag=None,
            conditional_response=False,
            app_iter=iter([b"foo"]),
            content_length=None,
        )
        handler = pretend.call_recorder(lambda request: response)
        request = pretend.stub(method="GET")

        tween = conditional_http_tween_factory(handler, pretend.stub())

        assert tween(request) is response
        assert handler.calls == [pretend.call(request)]
        assert response.conditional_response

    def test_explicit_etag(self):
        response = pretend.stub(
            last_modified=None,
            etag="foo",
            conditional_response=False,
            app_iter=iter([b"foo"]),
        )
        handler = pretend.call_recorder(lambda request: response)
        request = pretend.stub()

        tween = conditional_http_tween_factory(handler, pretend.stub())

        assert tween(request) is response
        assert handler.calls == [pretend.call(request)]
        assert response.conditional_response

    @pytest.mark.parametrize("method", ["GET", "HEAD"])
    def test_implicit_etag(self, method):
        response = pretend.stub(
            last_modified=None,
            etag=None,
            conditional_response=False,
            md5_etag=pretend.call_recorder(lambda: None),
            app_iter=[b"foo"],
            status_code=200,
        )
        handler = pretend.call_recorder(lambda request: response)
        request = pretend.stub(method=method)

        tween = conditional_http_tween_factory(handler, pretend.stub())

        assert tween(request) is response
        assert handler.calls == [pretend.call(request)]
        assert response.conditional_response
        assert response.md5_etag.calls == [pretend.call()]

    @pytest.mark.parametrize("method", ["GET", "HEAD"])
    def test_implicit_etag_buffers_streaming(self, method):
        response = pretend.stub(
            last_modified=None,
            etag=None,
            conditional_response=False,
            md5_etag=pretend.call_recorder(lambda: None),
            app_iter=iter([b"foo"]),
            body=b"foo",
            content_length=3,
            status_code=200,
        )
        handler = pretend.call_recorder(lambda request: response)
        request = pretend.stub(method=method)

        tween = conditional_http_tween_factory(handler, pretend.stub())

        assert tween(request) is response
        assert handler.calls == [pretend.call(request)]
        assert response.conditional_response
        assert response.md5_etag.calls == [pretend.call()]

    @pytest.mark.parametrize("method", ["GET", "HEAD"])
    def test_no_implicit_etag_no_200(self, method):
        response = pretend.stub(
            last_modified=None,
            etag=None,
            conditional_response=False,
            md5_etag=pretend.call_recorder(lambda: None),
            app_iter=[b"foo"],
            status_code=201,
        )
        handler = pretend.call_recorder(lambda request: response)
        request = pretend.stub(method=method)

        tween = conditional_http_tween_factory(handler, pretend.stub())

        assert tween(request) is response
        assert handler.calls == [pretend.call(request)]
        assert not response.conditional_response
        assert response.md5_etag.calls == []

    @pytest.mark.parametrize("method", ["POST", "PUT"])
    def test_no_implicit_etag_wrong_method(self, method):
        response = pretend.stub(
            last_modified=None,
            etag=None,
            conditional_response=False,
            md5_etag=pretend.call_recorder(lambda: None),
            app_iter=[b"foo"],
            status_code=200,
        )
        handler = pretend.call_recorder(lambda request: response)
        request = pretend.stub(method=method)

        tween = conditional_http_tween_factory(handler, pretend.stub())

        assert tween(request) is response
        assert handler.calls == [pretend.call(request)]
        assert not response.conditional_response
        assert response.md5_etag.calls == []

    def test_no_etag(self):
        response = pretend.stub(
            status_code=200,
            last_modified=None,
            etag=None,
            conditional_response=False,
            app_iter=iter([b"foo"]),
            content_length=None,
        )
        handler = pretend.call_recorder(lambda request: response)
        request = pretend.stub(method="GET")

        tween = conditional_http_tween_factory(handler, pretend.stub())

        assert tween(request) is response
        assert handler.calls == [pretend.call(request)]
        assert not response.conditional_response


def test_includeme():
    config = pretend.stub(add_tween=pretend.call_recorder(lambda t: None))
    includeme(config)

    assert config.add_tween.calls == [
        pretend.call("warehouse.cache.http.conditional_http_tween_factory")
    ]
