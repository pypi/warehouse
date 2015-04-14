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

from pyramid.httpexceptions import HTTPMethodNotAllowed

from warehouse.utils.http import (
    require_http_method, require_POST, require_GET, require_safe, is_safe_url,
)


class TestRequireHTTPMethod:

    @pytest.mark.parametrize(
        ("allowed", "method"),
        [
            (["GET", "HEAD", "POST"], "GET"),
            (["GET", "HEAD", "POST"], "HEAD"),
            (["GET", "HEAD", "POST"], "POST"),
            (["POST"], "POST"),
        ],
    )
    def test_allows_methods(self, allowed, method):
        @require_http_method(*allowed)
        @pretend.call_recorder
        def view(context, request):
            assert request.method == method

        request = pretend.stub(method=method)
        view(None, request)

        assert view.calls == [pretend.call(None, request)]

    @pytest.mark.parametrize(
        ("allowed", "method"),
        [
            (["GET", "HEAD", "POST"], "PUT"),
            (["GET", "HEAD", "POST"], "DELETE"),
            (["GET", "HEAD", "POST"], "OPTIONS"),
            (["POST"], "GET"),
            (["GET", "HEAD"], "POST"),
        ],
    )
    def test_rejects_methods(self, allowed, method):
        @require_http_method(*allowed)
        @pretend.call_recorder
        def view(context, request):
            assert False, "We should never be able to reach this code."

        with pytest.raises(HTTPMethodNotAllowed) as exc_info:
            view(None, pretend.stub(method=method))

        assert exc_info.value.headers["Allow"] == ", ".join(sorted(allowed))
        assert view.calls == []

    @pytest.mark.parametrize(
        ("deco", "method"),
        [
            (require_POST, "POST"),
            (require_GET, "GET"),
            (require_safe, "GET"),
            (require_safe, "HEAD"),
        ],
    )
    def test_require_static_valid(self, deco, method):
        @deco
        @pretend.call_recorder
        def view(context, request):
            assert request.method == method

        request = pretend.stub(method=method)
        view(None, request)

        assert view.calls == [pretend.call(None, request)]

    @pytest.mark.parametrize(
        ("deco", "method", "allowed"),
        [
            (require_POST, "GET", ["POST"]),
            (require_POST, "HEAD", ["POST"]),
            (require_GET, "POST", ["GET"]),
            (require_GET, "HEAD", ["GET"]),
            (require_safe, "POST", ["GET", "HEAD"]),
        ],
    )
    def test_require_static_invalid(self, deco, method, allowed):
        @deco
        @pretend.call_recorder
        def view(context, request):
            assert False, "We should never be able to reach this code."

        with pytest.raises(HTTPMethodNotAllowed) as exc_info:
            view(None, pretend.stub(method=method))

        assert exc_info.value.headers["Allow"] == ", ".join(sorted(allowed))
        assert view.calls == []


# (MOSTLY) FROM https://github.com/django/django/blob/
# 011a54315e46acdf288003566b8570440f5ac985/tests/utils_tests/test_http.py
class TestIsSafeUrl:

    @pytest.mark.parametrize(
        "url",
        [
            None,
            'http://example.com',
            'http:///example.com',
            'https://example.com',
            'ftp://exampel.com',
            r'\\example.com',
            r'\\\example.com',
            r'/\\/example.com',
            r'\\\example.com',
            r'\\example.com',
            r'\\//example.com',
            r'/\/example.com',
            r'\/example.com',
            r'/\example.com',
            'http:///example.com',
            'http:/\//example.com',
            'http:\/example.com',
            'http:/\example.com',
            'javascript:alert("XSS")',
            '\njavascript:alert(x)',
            '\x08//example.com',
            '\n',
        ],
    )
    def test_rejects_bad_url(self, url):
        assert not is_safe_url(url, host="testserver")

    @pytest.mark.parametrize(
        "url",
        [
            '/view/?param=http://example.com',
            '/view/?param=https://example.com',
            '/view?param=ftp://exampel.com',
            'view/?param=//example.com',
            'https://testserver/',
            'HTTPS://testserver/',
            '//testserver/',
            '/url%20with%20spaces/',
        ],
    )
    def test_accepts_good_url(self, url):
        assert is_safe_url(url, host="testserver")
