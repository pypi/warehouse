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

import pretend
import pytest

from pyramid.response import Response
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
    def test_bails_if_vary(self, vary):
        request = pretend.stub()
        response = pretend.stub(vary=vary)

        compressor(request, response)

    def test_bails_if_content_encoding(self):
        request = pretend.stub()
        response = pretend.stub(headers={"Content-Encoding": "something"}, vary=None)

        compressor(request, response)

    @pytest.mark.parametrize(
        ("vary", "expected"),
        [
            (None, {"Accept-Encoding"}),
            (["Something-Else"], {"Accept-Encoding", "Something-Else"}),
        ],
    )
    def test_sets_vary(self, vary, expected):
        request = pretend.stub(accept_encoding=AcceptEncodingNoHeader())
        response = Response(body=b"foo")
        response.vary = vary

        compressor(request, response)

        assert set(response.vary) == expected

    def test_compresses_non_streaming(self):
        decompressed_body = b"foofoofoofoofoofoofoofoofoofoofoofoofoofoo"
        compressed_body = b"".join(list(gzip_app_iter([decompressed_body])))

        request = pretend.stub(accept_encoding=AcceptEncodingValidHeader("gzip"))
        response = Response(body=decompressed_body)
        response.md5_etag()

        original_etag = response.etag

        compressor(request, response)

        assert response.content_encoding == "gzip"
        assert response.content_length == len(compressed_body)
        assert response.body == compressed_body
        assert response.etag != original_etag

    def test_compresses_streaming(self):
        decompressed_body = b"foofoofoofoofoofoofoofoofoofoofoofoofoofoo"
        compressed_body = b"".join(list(gzip_app_iter([decompressed_body])))

        request = pretend.stub(accept_encoding=AcceptEncodingValidHeader("gzip"))
        response = Response(app_iter=iter([decompressed_body]))

        compressor(request, response)

        assert response.content_encoding == "gzip"
        assert response.content_length is None
        assert response.body == compressed_body

    def test_compresses_streaming_with_etag(self):
        decompressed_body = b"foofoofoofoofoofoofoofoofoofoofoofoofoofoo"
        compressed_body = b"".join(list(gzip_app_iter([decompressed_body])))

        request = pretend.stub(accept_encoding=AcceptEncodingValidHeader("gzip"))
        response = Response(app_iter=iter([decompressed_body]))
        response.etag = "foo"

        compressor(request, response)

        assert response.content_encoding == "gzip"
        assert response.content_length is None
        assert response.body == compressed_body
        assert response.etag == "rfbezwKUdGjz6VPWDLDTvA"

    def test_buffers_small_streaming(self):
        decompressed_body = b"foofoofoofoofoofoofoofoofoofoofoofoofoofoo"
        compressed_body = b"".join(list(gzip_app_iter([decompressed_body])))

        request = pretend.stub(accept_encoding=AcceptEncodingValidHeader("gzip"))
        response = Response(
            app_iter=iter([decompressed_body]), content_length=len(decompressed_body)
        )

        compressor(request, response)

        assert response.content_encoding == "gzip"
        assert response.content_length == len(compressed_body)
        assert response.body == compressed_body

    def test_doesnt_compress_too_small(self):
        request = pretend.stub(accept_encoding=AcceptEncodingValidHeader("gzip"))
        response = Response(body=b"foo")

        compressor(request, response)

        assert response.content_encoding is None
        assert response.content_length == 3
        assert response.body == b"foo"


def test_compression_tween_factory():
    callbacks = []

    registry = pretend.stub()
    request = pretend.stub(add_response_callback=callbacks.append)
    response = pretend.stub()

    def handler(inner_request):
        assert inner_request is request
        return response

    tween = compression_tween_factory(handler, registry)

    assert tween(request) is response
    assert callbacks == [compressor]
