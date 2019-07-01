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

import pytest

from warehouse.utils.http import is_safe_url, is_valid_uri


# (MOSTLY) FROM https://github.com/django/django/blob/
# 011a54315e46acdf288003566b8570440f5ac985/tests/utils_tests/test_http.py
class TestIsSafeUrl:
    @pytest.mark.parametrize(
        "url",
        [
            None,
            "http://example.com",
            "http:///example.com",
            "https://example.com",
            "ftp://exampel.com",
            r"\\example.com",
            r"\\\example.com",
            r"/\\/example.com",
            r"\\\example.com",
            r"\\example.com",
            r"\\//example.com",
            r"/\/example.com",
            r"\/example.com",
            r"/\example.com",
            "http:///example.com",
            r"http:/\//example.com",
            r"http:\/example.com",
            r"http:/\example.com",
            'javascript:alert("XSS")',
            "\njavascript:alert(x)",
            "\x08//example.com",
            "\n",
        ],
    )
    def test_rejects_bad_url(self, url):
        assert not is_safe_url(url, host="testserver")

    @pytest.mark.parametrize(
        "url",
        [
            "/view/?param=http://example.com",
            "/view/?param=https://example.com",
            "/view?param=ftp://exampel.com",
            "view/?param=//example.com",
            "https://testserver/",
            "HTTPS://testserver/",
            "//testserver/",
            "/url%20with%20spaces/",
        ],
    )
    def test_accepts_good_url(self, url):
        assert is_safe_url(url, host="testserver")


class TestIsValidURI:
    @pytest.mark.parametrize(
        "uri",
        [
            "https://example.com/",
            "http://example.com/",
            "https://sub.example.com/path?query#thing",
        ],
    )
    def test_valid(self, uri):
        assert is_valid_uri(uri)

    @pytest.mark.parametrize(
        "uri", ["javascript:alert(0)", "UNKNOWN", "ftp://example.com/", ""]
    )
    def test_invalid(self, uri):
        assert not is_valid_uri(uri)

    def test_plain_schemes(self):
        assert is_valid_uri(
            "ftp://example.com/", require_scheme=True, allowed_schemes=[]
        )

    def test_scheme_not_required(self):
        assert is_valid_uri("//example.com", require_scheme=False)

    def test_authority_not_required(self):
        assert is_valid_uri("http://", require_authority=False)
