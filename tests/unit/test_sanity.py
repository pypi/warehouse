# SPDX-License-Identifier: Apache-2.0

import io
import re

import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPMovedPermanently, HTTPOk
from pyramid.request import Request
from pyramid.response import Response

from warehouse import sanity


class TestJunkEncoding:
    def test_valid(self):
        request = Request({"QUERY_STRING": ":action=browse", "PATH_INFO": "/pypi"})
        sanity.junk_encoding(request)

    def test_invalid_qsl(self):
        request = Request({"QUERY_STRING": "%Aaction=browse"})

        with pytest.raises(
            HTTPBadRequest, match=re.escape("Invalid bytes in query string.")
        ):
            sanity.junk_encoding(request)

    def test_invalid_path(self):
        request = Request({"PATH_INFO": "/projects/abouÅt"})

        with pytest.raises(HTTPBadRequest, match=re.escape("Invalid bytes in URL.")):
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
                    b'Content-Disposition: form-data; name="person"\r\nanonymous'
                ),
            }
        )

        with pytest.raises(HTTPBadRequest, match=re.escape("Invalid Form Data.")):
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
    resp_in = HTTPMovedPermanently(original_location) if original_location else HTTPOk()

    resp_out = sanity.unicode_redirects(resp_in)

    assert resp_out.location == expected_location


class TestSanityTween:
    def test_ingress_valid(self, mocker):
        junk_encoding = mocker.spy(sanity, "junk_encoding")
        invalid_forms = mocker.spy(sanity, "invalid_forms")
        response = Response()
        handler = mocker.create_autospec(lambda request: None, return_value=response)
        request = Request.blank("/")

        tween = sanity.sanity_tween_factory_ingress(handler, mocker.sentinel.registry)

        assert tween(request) is response
        junk_encoding.assert_called_once_with(request)
        invalid_forms.assert_called_once_with(request)
        handler.assert_called_once_with(request)

    def test_ingress_invalid(self, mocker):
        response = HTTPBadRequest()
        junk_encoding = mocker.patch.object(
            sanity, "junk_encoding", autospec=True, side_effect=response
        )
        invalid_forms = mocker.spy(sanity, "invalid_forms")
        handler = mocker.create_autospec(lambda request: None)
        request = Request.blank("/")

        tween = sanity.sanity_tween_factory_ingress(handler, mocker.sentinel.registry)

        assert tween(request) is response
        junk_encoding.assert_called_once_with(request)
        invalid_forms.assert_not_called()
        handler.assert_not_called()

    def test_egress(self, mocker):
        unicode_redirects = mocker.patch.object(
            sanity,
            "unicode_redirects",
            autospec=True,
            return_value=mocker.sentinel.redirected_response,
        )
        response = Response()
        handler = mocker.create_autospec(lambda request: None, return_value=response)
        request = Request.blank("/")

        tween = sanity.sanity_tween_factory_egress(handler, mocker.sentinel.registry)

        assert tween(request) is mocker.sentinel.redirected_response
        handler.assert_called_once_with(request)
        unicode_redirects.assert_called_once_with(response)
