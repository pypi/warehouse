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

from warehouse.utils.http import is_safe_url


class TestHttp:

    # (MOSTLY) FROM https://github.com/django/django/blob/
    # 011a54315e46acdf288003566b8570440f5ac985/tests/utils_tests/test_http.py
    def test_is_safe_url(self):
        # A None URL is not safe!
        assert not is_safe_url(None)

        for bad_url in ('http://example.com',
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
                        '\n'):
            assert not is_safe_url(bad_url, host='testserver'),\
                "{} should be blocked".format(bad_url)

        for good_url in ('/view/?param=http://example.com',
                         '/view/?param=https://example.com',
                         '/view?param=ftp://exampel.com',
                         'view/?param=//example.com',
                         'https://testserver/',
                         'HTTPS://testserver/',
                         '//testserver/',
                         '/url%20with%20spaces/'):
            assert is_safe_url(good_url, host='testserver'),\
                "{} should be allowed".format(good_url)
