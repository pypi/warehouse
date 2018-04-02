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

from warehouse.utils import wsgi


class TestProxyFixer:

    def test_skips_headers(self):
        response = pretend.stub()
        app = pretend.call_recorder(lambda e, s: response)

        environ = {
            "HTTP_WAREHOUSE_TOKEN": "NOPE",
            "HTTP_WAREHOUSE_PROTO": "http",
            "HTTP_WAREHOUSE_IP": "1.2.3.4",
            "HTTP_WAREHOUSE_HOST": "example.com",
        }
        start_response = pretend.stub()

        resp = wsgi.ProxyFixer(app, token="1234")(environ, start_response)

        assert resp is response
        assert app.calls == [pretend.call({}, start_response)]

    def test_accepts_warehouse_headers(self):
        response = pretend.stub()
        app = pretend.call_recorder(lambda e, s: response)

        environ = {
            "HTTP_WAREHOUSE_TOKEN": "1234",
            "HTTP_WAREHOUSE_PROTO": "http",
            "HTTP_WAREHOUSE_IP": "1.2.3.4",
            "HTTP_WAREHOUSE_HOST": "example.com",
        }
        start_response = pretend.stub()

        resp = wsgi.ProxyFixer(app, token="1234")(environ, start_response)

        assert resp is response
        assert app.calls == [
            pretend.call(
                {
                    "REMOTE_ADDR": "1.2.3.4",
                    "HTTP_HOST": "example.com",
                    "wsgi.url_scheme": "http",
                },
                start_response,
            ),
        ]

    def test_missing_headers(self):
        response = pretend.stub()
        app = pretend.call_recorder(lambda e, s: response)

        environ = {"HTTP_WAREHOUSE_TOKEN": "1234"}
        start_response = pretend.stub()

        resp = wsgi.ProxyFixer(app, token="1234")(environ, start_response)

        assert resp is response
        assert app.calls == [pretend.call({}, start_response)]

    def test_accepts_x_forwarded_headers(self):
        response = pretend.stub()
        app = pretend.call_recorder(lambda e, s: response)

        environ = {
            "HTTP_X_FORWARDED_PROTO": "http",
            "HTTP_X_FORWARDED_FOR": "1.2.3.4",
            "HTTP_X_FORWARDED_HOST": "example.com",
            "HTTP_SOME_OTHER_HEADER": "woop",
        }
        start_response = pretend.stub()

        resp = wsgi.ProxyFixer(app, token=None)(environ, start_response)

        assert resp is response
        assert app.calls == [
            pretend.call(
                {
                    "HTTP_SOME_OTHER_HEADER": "woop",
                    "REMOTE_ADDR": "1.2.3.4",
                    "HTTP_HOST": "example.com",
                    "wsgi.url_scheme": "http",
                },
                start_response,
            ),
        ]

    def test_skips_x_forwarded_when_not_enough(self):
        response = pretend.stub()
        app = pretend.call_recorder(lambda e, s: response)

        environ = {
            "HTTP_X_FORWARDED_FOR": "1.2.3.4",
            "HTTP_SOME_OTHER_HEADER": "woop",
        }
        start_response = pretend.stub()

        resp = wsgi.ProxyFixer(app, token=None, num_proxies=2)(
            environ,
            start_response,
        )

        assert resp is response
        assert app.calls == [
            pretend.call({"HTTP_SOME_OTHER_HEADER": "woop"}, start_response),
        ]

    def test_selects_right_x_forwarded_value(self):
        response = pretend.stub()
        app = pretend.call_recorder(lambda e, s: response)

        environ = {
            "HTTP_X_FORWARDED_PROTO": "http",
            "HTTP_X_FORWARDED_FOR": "2.2.3.4, 1.2.3.4, 5.5.5.5",
            "HTTP_X_FORWARDED_HOST": "example.com",
            "HTTP_SOME_OTHER_HEADER": "woop",
        }
        start_response = pretend.stub()

        resp = wsgi.ProxyFixer(app, token=None, num_proxies=2)(
            environ,
            start_response,
        )

        assert resp is response
        assert app.calls == [
            pretend.call(
                {
                    "HTTP_SOME_OTHER_HEADER": "woop",
                    "REMOTE_ADDR": "1.2.3.4",
                    "HTTP_HOST": "example.com",
                    "wsgi.url_scheme": "http",
                },
                start_response,
            ),
        ]


class TestVhmRootRemover:

    def test_removes_header(self):
        response = pretend.stub()
        app = pretend.call_recorder(lambda e, s: response)
        environ = {"HTTP_X_VHM_ROOT": "/foo/bar"}
        start_response = pretend.stub()

        resp = wsgi.VhmRootRemover(app)(environ, start_response)

        assert resp is response
        assert app.calls == [pretend.call({}, start_response)]

    def test_passes_through_headers(self):
        response = pretend.stub()
        app = pretend.call_recorder(lambda e, s: response)
        environ = {"HTTP_X_FOOBAR": "wat"}
        start_response = pretend.stub()

        resp = wsgi.VhmRootRemover(app)(environ, start_response)

        assert resp is response
        assert app.calls == [
            pretend.call({"HTTP_X_FOOBAR": "wat"}, start_response),
        ]


class TestHostRewrite:

    def test_rewrites_host(self):
        response = pretend.stub()
        app = pretend.call_recorder(lambda e, s: response)
        environ = {"HTTP_HOST": "upload.pypi.io"}
        start_response = pretend.stub()

        resp = wsgi.HostRewrite(app)(environ, start_response)

        assert resp is response
        assert app.calls == [
            pretend.call({"HTTP_HOST": "upload.pypi.org"}, start_response),
        ]

    def test_ignores_other_hosts(self):
        response = pretend.stub()
        app = pretend.call_recorder(lambda e, s: response)
        environ = {"HTTP_HOST": "example.com"}
        start_response = pretend.stub()

        resp = wsgi.HostRewrite(app)(environ, start_response)

        assert resp is response
        assert app.calls == [
            pretend.call({"HTTP_HOST": "example.com"}, start_response),
        ]
