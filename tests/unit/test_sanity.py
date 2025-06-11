# SPDX-License-Identifier: Apache-2.0

import io

import pretend
import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPMovedPermanently, HTTPOk
from pyramid.request import Request

from warehouse import sanity


class TestJunkEncoding:
    def test_valid(self):
        request = Request({"QUERY_STRING": ":action=browse", "PATH_INFO": "/pypi"})
        sanity.junk_encoding(request)

    def test_invalid_qsl(self):
        request = Request({"QUERY_STRING": "%Aaction=browse"})

        with pytest.raises(HTTPBadRequest, match="Invalid bytes in query string."):
            sanity.junk_encoding(request)

    def test_invalid_path(self):
        request = Request({"PATH_INFO": "/projects/abouÅt"})

        with pytest.raises(HTTPBadRequest, match="Invalid bytes in URL."):
            sanity.junk_encoding(request)


class TestInvalidForms:
    def test_valid(self):
        request = Request(
            {
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": (
                    "multipart/form-data; boundary=c397e2aa2980f1a53dee37c05b8fb45a"
                ),
                "wsgi.input": io.BytesIO(
                    b"--------------------------c397e2aa2980f1a53dee37c05b8fb45a\r\n"
                    b'Content-Disposition: form-data; name="person"\r\n'
                    b"anonymous"
                ),
            }
        )

        sanity.invalid_forms(request)

    def test_invalid_form(self):
        request = Request(
            {
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": ("multipart/form-data"),
                "wsgi.input": io.BytesIO(
                    b'Content-Disposition: form-data; name="person"\r\n' b"anonymous"
                ),
            }
        )

        with pytest.raises(HTTPBadRequest, match="Invalid Form Data."):
            sanity.invalid_forms(request)

    def test_not_post(self):
        request = Request({"REQUEST_METHOD": "GET"})
        sanity.invalid_forms(request)


@pytest.mark.parametrize(
    ("original_location", "expected_location"),
    [
        ("/a/path/to/nowhere", "/a/path/to/nowhere"),
        ("/project/☃/", "/project/%E2%98%83/"),
        (None, None),
    ],
)
def test_unicode_redirects(original_location, expected_location):
    if original_location:
        resp_in = HTTPMovedPermanently(original_location)
    else:
        resp_in = HTTPOk()

    resp_out = sanity.unicode_redirects(resp_in)

    assert resp_out.location == expected_location


class TestSanityTween:
    def test_ingress_valid(self, monkeypatch):
        junk_encoding = pretend.call_recorder(lambda request: None)
        monkeypatch.setattr(sanity, "junk_encoding", junk_encoding)

        invalid_forms = pretend.call_recorder(lambda request: None)
        monkeypatch.setattr(sanity, "invalid_forms", invalid_forms)

        response = pretend.stub()
        handler = pretend.call_recorder(lambda request: response)
        registry = pretend.stub()

        request = pretend.stub()

        tween = sanity.sanity_tween_factory_ingress(handler, registry)

        assert tween(request) is response
        assert junk_encoding.calls == [pretend.call(request)]
        assert invalid_forms.calls == [pretend.call(request)]
        assert handler.calls == [pretend.call(request)]

    def test_ingress_invalid(self, monkeypatch):
        response = HTTPBadRequest()

        @pretend.call_recorder
        def junk_encoding(request):
            raise response

        monkeypatch.setattr(sanity, "junk_encoding", junk_encoding)

        handler = pretend.call_recorder(lambda request: response)
        registry = pretend.stub()

        request = pretend.stub()

        tween = sanity.sanity_tween_factory_ingress(handler, registry)

        assert tween(request) is response
        assert junk_encoding.calls == [pretend.call(request)]
        assert handler.calls == []

    def test_egress(self, monkeypatch):
        unicode_redirects = pretend.call_recorder(lambda resp: resp)
        monkeypatch.setattr(sanity, "unicode_redirects", unicode_redirects)

        response = pretend.stub()
        handler = pretend.call_recorder(lambda request: response)
        registry = pretend.stub()

        request = pretend.stub()

        tween = sanity.sanity_tween_factory_egress(handler, registry)

        assert tween(request) is response
        assert handler.calls == [pretend.call(request)]
        assert unicode_redirects.calls == [pretend.call(response)]
