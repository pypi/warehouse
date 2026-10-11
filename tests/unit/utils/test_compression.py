# SPDX-License-Identifier: Apache-2.0

import pytest

from pyramid.httpexceptions import HTTPOk
from webob.acceptparse import AcceptEncodingNoHeader, AcceptEncodingValidHeader
from webob.response import gzip_app_iter

from warehouse.utils.compression import (
    _compressor as compressor,
    compression_tween_factory,
)


class TestCompressor:
    @pytest.mark.parametrize(
        "vary", [["Cookie"], ["Authorization"], ["Cookie", "Authorization"]]
    )
    def test_bails_if_vary(self, vary, mocker):
        request = mocker.sentinel.request
        response = HTTPOk()
        response.vary = vary

        compressor(request, response)

    def test_bails_if_content_encoding(self, mocker):
        request = mocker.sentinel.request
        response = HTTPOk()
        response.content_encoding = "something"

        compressor(request, response)

    @pytest.mark.parametrize(
        ("vary", "expected"),
        [
            (None, {"Accept-Encoding"}),
            (["Something-Else"], {"Accept-Encoding", "Something-Else"}),
        ],
    )
    def test_sets_vary(self, vary, expected, pyramid_request):
        pyramid_request.accept_encoding = AcceptEncodingNoHeader()
        response = HTTPOk(body=b"foo")
        response.vary = vary

        compressor(pyramid_request, response)

        assert set(response.vary) == expected

    def test_compresses_non_streaming(self, pyramid_request):
        decompressed_body = b"foofoofoofoofoofoofoofoofoofoofoofoofoofoo"
        compressed_body = b"".join(list(gzip_app_iter([decompressed_body])))

        pyramid_request.accept_encoding = AcceptEncodingValidHeader("gzip")
        response = HTTPOk(body=decompressed_body)
        response.md5_etag()

        original_etag = response.etag

        compressor(pyramid_request, response)

        assert response.content_encoding == "gzip"
        assert response.content_length == len(compressed_body)
        assert response.body == compressed_body
        assert response.etag != original_etag

    def test_compresses_streaming(self, pyramid_request):
        decompressed_body = b"foofoofoofoofoofoofoofoofoofoofoofoofoofoo"
        compressed_body = b"".join(list(gzip_app_iter([decompressed_body])))

        pyramid_request.accept_encoding = AcceptEncodingValidHeader("gzip")
        response = HTTPOk(app_iter=iter([decompressed_body]))

        compressor(pyramid_request, response)

        assert response.content_encoding == "gzip"
        assert response.content_length is None
        assert response.body == compressed_body

    def test_compresses_streaming_with_etag(self, pyramid_request):
        decompressed_body = b"foofoofoofoofoofoofoofoofoofoofoofoofoofoo"
        compressed_body = b"".join(list(gzip_app_iter([decompressed_body])))

        pyramid_request.accept_encoding = AcceptEncodingValidHeader("gzip")
        response = HTTPOk(app_iter=iter([decompressed_body]))
        response.etag = "foo"

        compressor(pyramid_request, response)

        assert response.content_encoding == "gzip"
        assert response.content_length is None
        assert response.body == compressed_body
        assert response.etag == "rfbezwKUdGjz6VPWDLDTvA"

    def test_buffers_small_streaming(self, pyramid_request):
        decompressed_body = b"foofoofoofoofoofoofoofoofoofoofoofoofoofoo"
        compressed_body = b"".join(list(gzip_app_iter([decompressed_body])))

        pyramid_request.accept_encoding = AcceptEncodingValidHeader("gzip")
        response = HTTPOk(
            app_iter=iter([decompressed_body]), content_length=len(decompressed_body)
        )

        compressor(pyramid_request, response)

        assert response.content_encoding == "gzip"
        assert response.content_length == len(compressed_body)
        assert response.body == compressed_body

    def test_doesnt_compress_too_small(self, pyramid_request):
        pyramid_request.accept_encoding = AcceptEncodingValidHeader("gzip")
        response = HTTPOk(body=b"foo")

        compressor(pyramid_request, response)

        assert response.content_encoding is None
        assert response.content_length == 3
        assert response.body == b"foo"


def test_compression_tween_factory(pyramid_request, mocker):
    registry = mocker.sentinel.registry
    response = mocker.sentinel.response

    def handler(inner_request):
        assert inner_request is pyramid_request
        return response

    tween = compression_tween_factory(handler, registry)

    assert tween(pyramid_request) is response
    assert list(pyramid_request.response_callbacks) == [compressor]
