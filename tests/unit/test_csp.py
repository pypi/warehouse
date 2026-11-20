# SPDX-License-Identifier: Apache-2.0

import collections

import pytest

from pyramid.response import Response

from warehouse import csp


class TestCSPTween:
    def test_csp_policy(self, mocker, pyramid_request, pyramid_services):
        response = Response()
        handler = mocker.create_autospec(lambda request: None, return_value=response)
        pyramid_services.register_service(
            csp.CSPPolicy(
                {"default-src": ["*"], "style-src": ["'self'", "example.net"]}
            ),
            name="csp",
        )
        pyramid_request.path = "/project/foobar/"

        tween = csp.content_security_policy_tween_factory(
            handler, pyramid_request.registry
        )

        assert tween(pyramid_request) is response
        handler.assert_called_once_with(pyramid_request)
        assert response.headers["Content-Security-Policy"] == (
            "default-src *; style-src 'self' example.net"
        )

    def test_csp_policy_default(self, mocker, pyramid_request):
        response = Response()
        handler = mocker.create_autospec(lambda request: None, return_value=response)
        pyramid_request.path = "/path/to/nowhere/"

        tween = csp.content_security_policy_tween_factory(
            handler, pyramid_request.registry
        )

        assert tween(pyramid_request) is response
        assert "Content-Security-Policy" not in response.headers

    @pytest.mark.parametrize("path", ["/_debug_toolbar/foo/", "/api/explorer/"])
    def test_csp_policy_excluded_paths(
        self, mocker, pyramid_request, pyramid_services, path
    ):
        response = Response()
        handler = mocker.create_autospec(lambda request: None, return_value=response)
        pyramid_services.register_service(
            csp.CSPPolicy(
                {"default-src": ["*"], "style-src": ["'self'", "example.net"]}
            ),
            name="csp",
        )
        pyramid_request.path = path

        tween = csp.content_security_policy_tween_factory(
            handler, pyramid_request.registry
        )

        assert tween(pyramid_request) is response
        assert "Content-Security-Policy" not in response.headers

    def test_csp_policy_inject(self, pyramid_request, pyramid_services):
        response = Response()

        def handler(request):
            request.find_service(name="csp")["default-src"].append("example.com")
            return response

        pyramid_services.register_service(
            csp.CSPPolicy({"default-src": ["*"], "style-src": ["'self'"]}), name="csp"
        )
        pyramid_request.path = "/example"

        tween = csp.content_security_policy_tween_factory(
            handler, pyramid_request.registry
        )

        assert tween(pyramid_request) is response
        assert response.headers["Content-Security-Policy"] == (
            "default-src * example.com; style-src 'self'"
        )

    def test_csp_policy_default_inject(self, pyramid_request, pyramid_services):
        response = Response()

        def handler(request):
            request.find_service(name="csp")["default-src"].append("example.com")
            return response

        pyramid_services.register_service(csp.CSPPolicy(), name="csp")
        pyramid_request.path = "/path/to/nowhere/"

        tween = csp.content_security_policy_tween_factory(
            handler, pyramid_request.registry
        )

        assert tween(pyramid_request) is response
        assert response.headers["Content-Security-Policy"] == "default-src example.com"

    def test_devel_csp(self, mocker, pyramid_request, pyramid_services):
        response = Response()
        handler = mocker.create_autospec(lambda request: None, return_value=response)
        pyramid_services.register_service(
            csp.CSPPolicy({"script-src": ["{request.scheme}://{request.host}"]}),
            name="csp",
        )
        pyramid_request.scheme = "https"
        pyramid_request.host = "example.com"
        pyramid_request.path = "/path/to/nowhere"

        tween = csp.content_security_policy_tween_factory(
            handler, pyramid_request.registry
        )

        assert tween(pyramid_request) is response
        assert response.headers["Content-Security-Policy"] == (
            "script-src https://example.com"
        )

    def test_simple_csp(self, mocker, pyramid_request, pyramid_services):
        response = Response()
        handler = mocker.create_autospec(lambda request: None, return_value=response)
        pyramid_services.register_service(
            csp.CSPPolicy({"default-src": ["*"], "script-src": ["'self'"]}),
            name="csp",
        )
        pyramid_request.path = "/simple/"

        tween = csp.content_security_policy_tween_factory(
            handler, pyramid_request.registry
        )

        assert tween(pyramid_request) is response
        assert response.headers["Content-Security-Policy"] == (
            "default-src 'none'; sandbox allow-top-navigation"
        )

    def test_admin_csp(self, mocker, pyramid_request, pyramid_services):
        response = Response()
        handler = mocker.create_autospec(lambda request: None, return_value=response)
        pyramid_services.register_service(
            csp.CSPPolicy(
                {
                    "default-src": ["'none'"],
                    "frame-src": ["'none'"],
                    "img-src": ["'self'"],
                    "connect-src": [],
                    "style-src": ["'self'"],
                }
            ),
            name="csp",
        )
        pyramid_request.registry.settings["camo.url"] = "http://localhost:9000"
        pyramid_request.path = "/admin/"

        tween = csp.content_security_policy_tween_factory(
            handler, pyramid_request.registry
        )

        assert tween(pyramid_request) is response
        assert response.headers["Content-Security-Policy"] == (
            "connect-src http://localhost:9000; "
            "default-src 'none'; "
            "frame-src https://inspector.pypi.io; "
            "img-src 'self' data:; "
            "style-src 'self' "
            "'sha256-kwpt3lQZ21rs4cld7/uEm9qI5yAbjYzx+9FGm/XmwNU='"
        )


class TestCSPPolicy:
    def test_create(self):
        policy = csp.CSPPolicy({"foo": ["bar"]})
        assert isinstance(policy, collections.defaultdict)

    @pytest.mark.parametrize(
        ("existing", "incoming", "expected"),
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


def test_includeme(mocker):
    config = mocker.Mock(
        spec=["register_service_factory", "add_settings", "add_tween", "registry"]
    )
    config.registry.settings = {
        "camo.url": "camo.url.value",
        "statuspage.url": "https://2p66nmmycsj3.statuspage.io",
    }
    csp.includeme(config)

    config.register_service_factory.assert_called_once_with(csp.csp_factory, name="csp")
    config.add_tween.assert_called_once_with(
        "warehouse.csp.content_security_policy_tween_factory"
    )
    config.add_settings.assert_called_once_with(
        {
            "csp": {
                "base-uri": ["'self'"],
                "connect-src": [
                    "'self'",
                    "https://api.github.com/repos/",
                    "https://api.github.com/search/issues",
                    "https://gitlab.com/api/",
                    "https://analytics.python.org",
                    "*.ethicalads.io",
                    "https://api.pwnedpasswords.com",
                    "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/sre/mathmaps/",
                    "https://2p66nmmycsj3.statuspage.io",
                ],
                "default-src": ["'none'"],
                "font-src": [
                    "'self'",
                ],
                "form-action": [
                    "'self'",
                    "https://checkout.stripe.com",
                    "https://billing.stripe.com",
                ],
                "frame-ancestors": ["'none'"],
                "frame-src": ["'none'"],
                "img-src": [
                    "'self'",
                    "camo.url.value",
                    "*.ethicalads.io",
                    "ethicalads.blob.core.windows.net",
                ],
                "script-src": [
                    "'self'",
                    "https://analytics.python.org",
                    "*.ethicalads.io",
                    "'sha256-U3hKDidudIaxBDEzwGJApJgPEf2mWk6cfMWghrAa6i0='",
                    "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/",
                    "'sha256-1CldwzdEg2k1wTmf7s5RWVd7NMXI/7nxxjJM2C4DqII='",
                ],
                "style-src": [
                    "'self'",
                    "*.ethicalads.io",
                    "'sha256-2YHqZokjiizkHi1Zt+6ar0XJ0OeEy/egBnlm+MDMtrM='",
                    "'sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU='",
                    "'sha256-JLEjeN9e5dGsz5475WyRaoA4eQOdNPxDIeUhclnJDCE='",
                    "'sha256-mQyxHEuwZJqpxCw3SLmc4YOySNKXunyu2Oiz1r3/wAE='",
                    "'sha256-OCf+kv5Asiwp++8PIevKBYSgnNLNUZvxAp4a7wMLuKA='",
                    "'sha256-h5LOiLhk6wiJrGsG5ItM0KimwzWQH/yAcmoJDJL//bY='",
                ],
            }
        }
    )


def test_includeme_development(mocker):
    """
    Tests for development-centric CSP settings.
    Not as extensive as the production tests.
    """
    config = mocker.Mock(
        spec=["register_service_factory", "add_settings", "add_tween", "registry"]
    )
    config.registry.settings = {
        "camo.url": "camo.url.value",
        "warehouse.env": "development",
        "livereload.url": "http://localhost:35729",
    }
    csp.includeme(config)

    config.add_settings.assert_called_once()
    rendered_csp = config.add_settings.call_args.args[0]["csp"]

    assert "ws://localhost:35729/livereload" in rendered_csp["connect-src"]
    assert "http://localhost:35729/livereload.js" in rendered_csp["script-src"]


class TestFactory:
    def test_copy(self, pyramid_request):
        settings = pyramid_request.registry.settings
        settings["csp"] = {"foo": "bar"}
        result = csp.csp_factory(None, pyramid_request)
        assert isinstance(result, csp.CSPPolicy)
        assert result == settings["csp"]

        # ensure changes to factory result don't propagate back to the
        # settings
        result["baz"] = "foo"
        assert result == {"foo": "bar", "baz": "foo"}
        assert settings["csp"] == {"foo": "bar"}

    def test_default(self, pyramid_request):
        result = csp.csp_factory(None, pyramid_request)
        assert isinstance(result, csp.CSPPolicy)
        assert result == {}
