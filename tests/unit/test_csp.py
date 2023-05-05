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
import pytest

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

    @pytest.mark.parametrize(
        "existing, incoming, expected",
        [
            (
                {"foo": ["bar"]},
                {"foo": ["baz"], "something": ["else"]},
                {"foo": ["bar", "baz"], "something": ["else"]},
            ),
            (
                {"foo": [csp.NONE]},
                {"foo": ["baz"]},
                {"foo": ["baz"]},
            ),
        ],
    )
    def test_merge(self, existing, incoming, expected):
        policy = csp.CSPPolicy(existing)
        policy.merge(incoming)
        assert policy == expected


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
                        "https://api.github.com/search/issues",
                        "https://*.google-analytics.com",
                        "https://*.analytics.google.com",
                        "https://*.googletagmanager.com",
                        "fastly-insights.com",
                        "*.fastly-insights.com",
                        "*.ethicalads.io",
                        "https://api.pwnedpasswords.com",
                        "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/sre/mathmaps/",
                        "https://2p66nmmycsj3.statuspage.io",
                    ],
                    "default-src": ["'none'"],
                    "font-src": ["'self'", "fonts.gstatic.com"],
                    "form-action": ["'self'", "https://checkout.stripe.com"],
                    "frame-ancestors": ["'none'"],
                    "frame-src": ["'none'"],
                    "img-src": [
                        "'self'",
                        "camo.url.value",
                        "https://*.google-analytics.com",
                        "https://*.googletagmanager.com",
                        "*.fastly-insights.com",
                        "*.ethicalads.io",
                    ],
                    "script-src": [
                        "'self'",
                        "https://*.googletagmanager.com",
                        "https://www.google-analytics.com",
                        "https://ssl.google-analytics.com",
                        "*.fastly-insights.com",
                        "*.ethicalads.io",
                        "'sha256-U3hKDidudIaxBDEzwGJApJgPEf2mWk6cfMWghrAa6i0='",
                        "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/",
                        "'sha256-1CldwzdEg2k1wTmf7s5RWVd7NMXI/7nxxjJM2C4DqII='",
                        "'sha256-0POaN8stWYQxhzjKS+/eOfbbJ/u4YHO5ZagJvLpMypo='",
                    ],
                    "style-src": [
                        "'self'",
                        "fonts.googleapis.com",
                        "*.ethicalads.io",
                        "'sha256-2YHqZokjiizkHi1Zt+6ar0XJ0OeEy/egBnlm+MDMtrM='",
                        "'sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU='",
                        "'sha256-JLEjeN9e5dGsz5475WyRaoA4eQOdNPxDIeUhclnJDCE='",
                        "'sha256-mQyxHEuwZJqpxCw3SLmc4YOySNKXunyu2Oiz1r3/wAE='",
                        "'sha256-OCf+kv5Asiwp++8PIevKBYSgnNLNUZvxAp4a7wMLuKA='",
                        "'sha256-h5LOiLhk6wiJrGsG5ItM0KimwzWQH/yAcmoJDJL//bY='",
                    ],
                    "worker-src": ["*.fastly-insights.com"],
                }
            }
        )
    ]


def test_includeme_development():
    """
    Tests for development-centric CSP settings.
    Not as extensive as the production tests.
    """
    config = pretend.stub(
        register_service_factory=pretend.call_recorder(lambda fact, name: None),
        add_settings=pretend.call_recorder(lambda settings: None),
        add_tween=pretend.call_recorder(lambda tween: None),
        registry=pretend.stub(
            settings={
                "camo.url": "camo.url.value",
                "warehouse.env": "development",
                "livereload.url": "http://localhost:35729",
            }
        ),
    )
    csp.includeme(config)

    rendered_csp = config.add_settings.calls[0].args[0]["csp"]

    assert config.registry.settings.get("warehouse.env") == "development"

    assert "ws://localhost:35729/livereload" in rendered_csp["connect-src"]
    assert "http://localhost:35729/livereload.js" in rendered_csp["script-src"]


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
