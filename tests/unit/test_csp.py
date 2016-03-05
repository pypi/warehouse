import collections

import pretend

from warehouse import csp


class TestCSPTween:

    def test_csp_policy(self):
        response = pretend.stub(headers={})
        handler = pretend.call_recorder(lambda request: response)
        settings = {
            "csp": {
                "default-src": ["*"],
                "style-src": ["'self'", "example.net"],
            },
        }
        registry = pretend.stub(settings=settings)

        tween = csp.content_security_policy_tween_factory(handler, registry)

        request = pretend.stub(
            path="/project/foobar/",
            find_service=pretend.call_recorder(
                lambda *args, **kwargs: settings["csp"]
            ),
        )

        assert tween(request) is response
        assert response.headers == {
            "Content-Security-Policy":
                "default-src *; style-src 'self' example.net",
        }

    def test_csp_policy_default(self):
        response = pretend.stub(headers={})
        handler = pretend.call_recorder(lambda request: response)
        registry = pretend.stub(settings={})

        tween = csp.content_security_policy_tween_factory(handler, registry)

        request = pretend.stub(
            path="/path/to/nowhere/",
            find_service=pretend.raiser(ValueError),
        )

        assert tween(request) is response
        assert response.headers == {}

    def test_csp_policy_debug_disables(self):
        response = pretend.stub(headers={})
        handler = pretend.call_recorder(lambda request: response)
        settings={
            "csp": {
                "default-src": ["*"],
                "style-src": ["'self'", "example.net"],
            },
        }

        registry = pretend.stub(settings=settings)

        tween = csp.content_security_policy_tween_factory(handler, registry)

        request = pretend.stub(
            path="/_debug_toolbar/foo/",
            find_service=pretend.call_recorder(
                lambda *args, **kwargs: settings["csp"]
            ),
        )

        assert tween(request) is response
        assert response.headers == {}

    def test_csp_policy_inject(self):
        response = pretend.stub(headers={})
        def handler(request):
            request.find_service("csp")["default-src"].append("example.com")
            return response

        settings = {
            "csp": {
                "default-src": ["*"],
                "style-src": ["'self'"],
            },
        }

        registry = pretend.stub(settings=settings)
        tween = csp.content_security_policy_tween_factory(handler, registry)

        request = pretend.stub(
            path="/example",
            find_service=pretend.call_recorder(
                lambda *args, **kwargs: settings["csp"]
            ),
        )

        assert tween(request) is response
        assert response.headers == {
            "Content-Security-Policy":
                "default-src * example.com; style-src 'self'",
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
            find_service=pretend.call_recorder(
                lambda *args, **kwargs: settings
            ),
        )

        assert tween(request) is response
        assert response.headers == {
            "Content-Security-Policy": "default-src example.com"
        }


def test_includeme():
    config = pretend.stub(
        register_service_factory=pretend.call_recorder(lambda fact, name: None),
        add_settings=pretend.call_recorder(lambda settings: None),
        add_tween=pretend.call_recorder(lambda tween: None),
        registry=pretend.stub(
            settings={
                "camo.url": "camo.url.value",
                "csp.report_uri": "csp.report_uri.value",
            }
        ),
    )
    csp.includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(csp.csp_factory, name="csp")
    ]

    assert config.add_tween.calls == [
        pretend.call("warehouse.csp.content_security_policy_tween_factory"),
    ]

    assert config.add_settings.calls == [
        pretend.call({
            "csp": {
                "connect-src": ["'self'"],
                "default-src": ["'none'"],
                "font-src": ["'self'", "fonts.gstatic.com"],
                "frame-ancestors": ["'none'"],
                "img-src": [
                    "'self'",
                    "camo.url.value",
                    "https://secure.gravatar.com",
                ],
                "referrer": ["origin-when-cross-origin"],
                "reflected-xss": ["block"],
                "report-uri": ["csp.report_uri.value"],
                "script-src": ["'self'"],
                "style-src": ["'self'", "fonts.googleapis.com"],
            },
        })
    ]
