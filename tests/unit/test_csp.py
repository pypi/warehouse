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

import collections

import pretend

from warehouse import csp


class TestCSPTween:
    def test_csp_policy(self):
        response = pretend.stub(headers={})
        handler = pretend.call_recorder(lambda request: response)
        settings = {
            "csp": {"default-src": ["*"], "style-src": ["'self'", "example.net"]}
        }
        registry = pretend.stub(settings=settings)

        tween = csp.content_security_policy_tween_factory(handler, registry)

        request = pretend.stub(
            path="/project/foobar/",
            find_service=pretend.call_recorder(lambda *args, **kwargs: settings["csp"]),
        )

        assert tween(request) is response
        assert response.headers == {
            "Content-Security-Policy": "default-src *; style-src 'self' example.net"
        }

    def test_csp_policy_default(self):
        response = pretend.stub(headers={})
        handler = pretend.call_recorder(lambda request: response)
        registry = pretend.stub(settings={})

        tween = csp.content_security_policy_tween_factory(handler, registry)

        request = pretend.stub(
            path="/path/to/nowhere/", find_service=pretend.raiser(LookupError)
        )

        assert tween(request) is response
        assert response.headers == {}

    def test_csp_policy_debug_disables(self):
        response = pretend.stub(headers={})
        handler = pretend.call_recorder(lambda request: response)
        settings = {
            "csp": {"default-src": ["*"], "style-src": ["'self'", "example.net"]}
        }

        registry = pretend.stub(settings=settings)

        tween = csp.content_security_policy_tween_factory(handler, registry)

        request = pretend.stub(
            path="/_debug_toolbar/foo/",
            find_service=pretend.call_recorder(lambda *args, **kwargs: settings["csp"]),
        )

        assert tween(request) is response
        assert response.headers == {}

    def test_csp_policy_inject(self):
        response = pretend.stub(headers={})

        def handler(request):
            request.find_service("csp")["default-src"].append("example.com")
            return response

        settings = {"csp": {"default-src": ["*"], "style-src": ["'self'"]}}

        registry = pretend.stub(settings=settings)
        tween = csp.content_security_policy_tween_factory(handler, registry)

        request = pretend.stub(
            path="/example",
            find_service=pretend.call_recorder(lambda *args, **kwargs: settings["csp"]),
        )

        assert tween(request) is response
        assert response.headers == {
            "Content-Security-Policy": "default-src * example.com; style-src 'self'"
        }

    def test_csp_policy_default_inject(self):
        settings = collections.defaultdict(list)
        response = pretend.stub(headers={})
        registry = pretend.stub(settings=settings)

        def handler(request):
            request.find_service("csp")["default-src"].append("example.com")
            return response

        tween = csp.content_security_policy_tween_factory(handler, registry)

        request = pretend.stub(
            path="/path/to/nowhere/",
            find_service=pretend.call_recorder(lambda *args, **kwargs: settings),
        )

        assert tween(request) is response
        assert response.headers == {
            "Content-Security-Policy": "default-src example.com"
        }

    def test_devel_csp(self):
        settings = {"csp": {"script-src": ["{request.scheme}://{request.host}"]}}
        response = pretend.stub(headers={})
        registry = pretend.stub(settings=settings)
        handler = pretend.call_recorder(lambda request: response)

        tween = csp.content_security_policy_tween_factory(handler, registry)

        request = pretend.stub(
            scheme="https",
            host="example.com",
            path="/path/to/nowhere",
            find_service=pretend.call_recorder(lambda *args, **kwargs: settings["csp"]),
        )

        assert tween(request) is response
        assert response.headers == {
            "Content-Security-Policy": "script-src https://example.com"
        }

    def test_simple_csp(self):
        settings = {
            "csp": {"default-src": ["'none'"], "sandbox": ["allow-top-navigation"]}
        }
        response = pretend.stub(headers={})
        registry = pretend.stub(settings=settings)
        handler = pretend.call_recorder(lambda request: response)

        tween = csp.content_security_policy_tween_factory(handler, registry)

        request = pretend.stub(
            scheme="https",
            host="example.com",
            path="/simple/",
            find_service=pretend.call_recorder(lambda *args, **kwargs: settings["csp"]),
        )

        assert tween(request) is response
        assert response.headers == {
            "Content-Security-Policy": (
                "default-src 'none'; sandbox allow-top-navigation"
            )
        }


class TestCSPPolicy:
    def test_create(self):
        policy = csp.CSPPolicy({"foo": ["bar"]})
        assert isinstance(policy, collections.defaultdict)

    def test_merge(self):
        policy = csp.CSPPolicy({"foo": ["bar"]})
        policy.merge({"foo": ["baz"], "something": ["else"]})
        assert policy == {"foo": ["bar", "baz"], "something": ["else"]}


def test_includeme():
    config = pretend.stub(
        register_service_factory=pretend.call_recorder(lambda fact, name: None),
        add_settings=pretend.call_recorder(lambda settings: None),
        add_tween=pretend.call_recorder(lambda tween: None),
        registry=pretend.stub(
            settings={
                "camo.url": "camo.url.value",
                "statuspage.url": "https://2p66nmmycsj3.statuspage.io",
            }
        ),
    )
    csp.includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(csp.csp_factory, name="csp")
    ]

    assert config.add_tween.calls == [
        pretend.call("warehouse.csp.content_security_policy_tween_factory")
    ]

    assert config.add_settings.calls == [
        pretend.call(
            {
                "csp": {
                    "base-uri": ["'self'"],
                    "block-all-mixed-content": [],
                    "connect-src": [
                        "'self'",
                        "https://api.github.com/repos/",
                        "*.fastly-insights.com",
                        "sentry.io",
                        "https://api.pwnedpasswords.com",
                        "https://2p66nmmycsj3.statuspage.io",
                    ],
                    "default-src": ["'none'"],
                    "font-src": ["'self'", "fonts.gstatic.com"],
                    "form-action": ["'self'"],
                    "frame-ancestors": ["'none'"],
                    "frame-src": ["'none'"],
                    "img-src": [
                        "'self'",
                        "camo.url.value",
                        "www.google-analytics.com",
                        "*.fastly-insights.com",
                    ],
                    "script-src": [
                        "'self'",
                        "www.googletagmanager.com",
                        "www.google-analytics.com",
                        "*.fastly-insights.com",
                        "https://cdn.ravenjs.com",
                    ],
                    "style-src": ["'self'", "fonts.googleapis.com"],
                    "worker-src": ["*.fastly-insights.com"],
                }
            }
        )
    ]


class TestFactory:
    def test_copy(self):
        settings = {"csp": {"foo": "bar"}}
        request = pretend.stub(registry=pretend.stub(settings=settings))
        result = csp.csp_factory(None, request)
        assert isinstance(result, csp.CSPPolicy)
        assert result == settings["csp"]

        # ensure changes to factory result don't propagate back to the
        # settings
        result["baz"] = "foo"
        assert result == {"foo": "bar", "baz": "foo"}
        assert settings == {"csp": {"foo": "bar"}}

    def test_default(self):
        request = pretend.stub(registry=pretend.stub(settings={}))
        result = csp.csp_factory(None, request)
        assert isinstance(result, csp.CSPPolicy)
        assert result == {}
