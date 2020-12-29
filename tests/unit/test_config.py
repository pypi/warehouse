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

from unittest import mock

import pretend
import pytest

from pyramid import renderers
from pyramid.tweens import EXCVIEW

from warehouse import config
from warehouse.errors import BasicAuthBreachedPassword
from warehouse.utils.wsgi import HostRewrite, ProxyFixer, VhmRootRemover


class TestRequireHTTPSTween:
    def test_noops_when_disabled(self):
        handler = pretend.stub()
        registry = pretend.stub(
            settings=pretend.stub(get=pretend.call_recorder(lambda k, v: False))
        )

        assert config.require_https_tween_factory(handler, registry) is handler
        assert registry.settings.get.calls == [pretend.call("enforce_https", True)]

    @pytest.mark.parametrize(
        ("params", "scheme"),
        [({}, "https"), ({":action": "thing"}, "https"), ({}, "http")],
    )
    def test_allows_through(self, params, scheme):
        request = pretend.stub(params=params, scheme=scheme)
        response = pretend.stub()
        handler = pretend.call_recorder(lambda req: response)
        registry = pretend.stub(settings=pretend.stub(get=lambda k, v: True))

        tween = config.require_https_tween_factory(handler, registry)

        assert tween(request) is response
        assert handler.calls == [pretend.call(request)]

    @pytest.mark.parametrize(("params", "scheme"), [({":action": "thing"}, "http")])
    def test_rejects(self, params, scheme):
        request = pretend.stub(params=params, scheme=scheme)
        handler = pretend.stub()
        registry = pretend.stub(settings=pretend.stub(get=lambda k, v: True))

        tween = config.require_https_tween_factory(handler, registry)
        resp = tween(request)

        assert resp.status == "403 SSL is required"
        assert resp.headers["X-Fastly-Error"] == "803"
        assert resp.content_type == "text/plain"
        assert resp.body == b"SSL is required."


@pytest.mark.parametrize(
    ("path", "expected"),
    [("/foo/bar/", True), ("/static/wat/", False), ("/_debug_toolbar/thing/", False)],
)
def test_activate_hook(path, expected):
    request = pretend.stub(path=path)
    assert config.activate_hook(request) == expected


@pytest.mark.parametrize(
    ("exc_info", "expected"),
    [
        (None, False),
        ((ValueError, ValueError(), None), True),
        ((BasicAuthBreachedPassword, BasicAuthBreachedPassword(), None), False),
    ],
)
def test_commit_veto(exc_info, expected):
    request = pretend.stub(exc_info=exc_info)
    response = pretend.stub()

    assert bool(config.commit_veto(request, response)) == expected


@pytest.mark.parametrize("route_kw", [None, {}, {"foo": "bar"}])
def test_template_view(route_kw):
    configobj = pretend.stub(
        add_route=pretend.call_recorder(lambda *a, **kw: None),
        add_view=pretend.call_recorder(lambda *a, **kw: None),
    )

    config.template_view(configobj, "test", "/test/", "test.html", route_kw=route_kw)

    assert configobj.add_route.calls == [
        pretend.call("test", "/test/", **({} if route_kw is None else route_kw))
    ]
    assert configobj.add_view.calls == [
        pretend.call(renderer="test.html", route_name="test")
    ]


@pytest.mark.parametrize(
    ("environ", "name", "envvar", "coercer", "default", "expected"),
    [
        ({}, "test.foo", "TEST_FOO", None, None, {}),
        ({"TEST_FOO": "bar"}, "test.foo", "TEST_FOO", None, None, {"test.foo": "bar"}),
        ({"TEST_INT": "1"}, "test.int", "TEST_INT", int, None, {"test.int": 1}),
        ({}, "test.foo", "TEST_FOO", None, "lol", {"test.foo": "lol"}),
        ({"TEST_FOO": "bar"}, "test.foo", "TEST_FOO", None, "lol", {"test.foo": "bar"}),
    ],
)
def test_maybe_set(monkeypatch, environ, name, envvar, coercer, default, expected):
    for key, value in environ.items():
        monkeypatch.setenv(key, value)
    settings = {}
    config.maybe_set(settings, name, envvar, coercer=coercer, default=default)
    assert settings == expected


@pytest.mark.parametrize(
    ("environ", "base", "name", "envvar", "expected"),
    [
        ({}, "test", "foo", "TEST_FOO", {}),
        ({"TEST_FOO": "bar"}, "test", "foo", "TEST_FOO", {"test.foo": "bar"}),
        (
            {"TEST_FOO": "bar thing=other"},
            "test",
            "foo",
            "TEST_FOO",
            {"test.foo": "bar", "test.thing": "other"},
        ),
        (
            {"TEST_FOO": 'bar thing=other wat="one two"'},
            "test",
            "foo",
            "TEST_FOO",
            {"test.foo": "bar", "test.thing": "other", "test.wat": "one two"},
        ),
    ],
)
def test_maybe_set_compound(monkeypatch, environ, base, name, envvar, expected):
    for key, value in environ.items():
        monkeypatch.setenv(key, value)
    settings = {}
    config.maybe_set_compound(settings, base, name, envvar)
    assert settings == expected


@pytest.mark.parametrize(
    ("settings", "environment", "other_settings"),
    [
        (None, config.Environment.production, {}),
        ({}, config.Environment.production, {}),
        ({"my settings": "the settings value"}, config.Environment.production, {}),
        (None, config.Environment.development, {}),
        ({}, config.Environment.development, {}),
        ({"my settings": "the settings value"}, config.Environment.development, {}),
        (None, config.Environment.production, {"warehouse.theme": "my_theme"}),
    ],
)
def test_configure(monkeypatch, settings, environment, other_settings):
    json_renderer_obj = pretend.stub()
    json_renderer_cls = pretend.call_recorder(lambda **kw: json_renderer_obj)
    monkeypatch.setattr(renderers, "JSON", json_renderer_cls)

    xmlrpc_renderer_obj = pretend.stub()
    xmlrpc_renderer_cls = pretend.call_recorder(lambda **kw: xmlrpc_renderer_obj)
    monkeypatch.setattr(config, "XMLRPCRenderer", xmlrpc_renderer_cls)

    if environment == config.Environment.development:
        monkeypatch.setenv("WAREHOUSE_ENV", "development")

    class FakeRegistry(dict):
        def __init__(self):
            self.settings = {
                "warehouse.token": "insecure token",
                "warehouse.env": environment,
                "camo.url": "http://camo.example.com/",
                "pyramid.reload_assets": False,
                "dirs.packages": "/srv/data/pypi/packages/",
                "warehouse.xmlrpc.client.ratelimit_string": "3600 per hour",
            }

    configurator_settings = other_settings.copy()
    configurator_obj = pretend.stub(
        registry=FakeRegistry(),
        set_root_factory=pretend.call_recorder(lambda rf: None),
        include=pretend.call_recorder(lambda include: None),
        add_directive=pretend.call_recorder(lambda name, fn, **k: None),
        add_wsgi_middleware=pretend.call_recorder(lambda m, *a, **kw: None),
        add_renderer=pretend.call_recorder(lambda name, renderer: None),
        add_request_method=pretend.call_recorder(lambda fn: None),
        add_jinja2_renderer=pretend.call_recorder(lambda renderer: None),
        add_jinja2_search_path=pretend.call_recorder(lambda path, name: None),
        get_settings=lambda: configurator_settings,
        add_settings=pretend.call_recorder(lambda d: configurator_settings.update(d)),
        add_tween=pretend.call_recorder(lambda tween_factory, **kw: None),
        add_static_view=pretend.call_recorder(lambda *a, **kw: None),
        add_cache_buster=pretend.call_recorder(lambda spec, buster: None),
        whitenoise_serve_static=pretend.call_recorder(lambda *a, **kw: None),
        whitenoise_add_files=pretend.call_recorder(lambda *a, **kw: None),
        whitenoise_add_manifest=pretend.call_recorder(lambda *a, **kw: None),
        scan=pretend.call_recorder(lambda ignore: None),
        commit=pretend.call_recorder(lambda: None),
    )
    configurator_cls = pretend.call_recorder(lambda settings: configurator_obj)
    monkeypatch.setattr(config, "Configurator", configurator_cls)

    cachebuster_obj = pretend.stub()
    cachebuster_cls = pretend.call_recorder(lambda p, **kw: cachebuster_obj)
    monkeypatch.setattr(config, "ManifestCacheBuster", cachebuster_cls)

    transaction_manager = pretend.stub()
    transaction = pretend.stub(
        TransactionManager=pretend.call_recorder(lambda: transaction_manager)
    )
    monkeypatch.setattr(config, "transaction", transaction)

    result = config.configure(settings=settings)

    expected_settings = {
        "warehouse.env": environment,
        "warehouse.commit": "null",
        "site.name": "Warehouse",
        "token.two_factor.max_age": 300,
        "token.default.max_age": 21600,
        "warehouse.xmlrpc.client.ratelimit_string": "3600 per hour",
        "warehouse.xmlrpc.search.enabled": True,
    }

    if environment == config.Environment.development:
        expected_settings.update(
            {
                "enforce_https": False,
                "pyramid.reload_templates": True,
                "pyramid.reload_assets": True,
                "pyramid.prevent_http_cache": True,
                "debugtoolbar.hosts": ["0.0.0.0/0"],
                "debugtoolbar.panels": [
                    "pyramid_debugtoolbar.panels.versions.VersionDebugPanel",
                    "pyramid_debugtoolbar.panels.settings.SettingsDebugPanel",
                    "pyramid_debugtoolbar.panels.headers.HeaderDebugPanel",
                    (
                        "pyramid_debugtoolbar.panels.request_vars."
                        "RequestVarsDebugPanel"
                    ),
                    "pyramid_debugtoolbar.panels.renderings.RenderingsDebugPanel",
                    "pyramid_debugtoolbar.panels.logger.LoggingPanel",
                    (
                        "pyramid_debugtoolbar.panels.performance."
                        "PerformanceDebugPanel"
                    ),
                    "pyramid_debugtoolbar.panels.routes.RoutesDebugPanel",
                    "pyramid_debugtoolbar.panels.sqla.SQLADebugPanel",
                    "pyramid_debugtoolbar.panels.tweens.TweensDebugPanel",
                    (
                        "pyramid_debugtoolbar.panels.introspection."
                        "IntrospectionDebugPanel"
                    ),
                ],
            }
        )

    if settings is not None:
        expected_settings.update(settings)

    assert configurator_cls.calls == [pretend.call(settings=expected_settings)]
    assert result is configurator_obj
    assert configurator_obj.set_root_factory.calls == [pretend.call(config.RootFactory)]
    assert configurator_obj.add_wsgi_middleware.calls == [
        pretend.call(ProxyFixer, token="insecure token", num_proxies=1),
        pretend.call(VhmRootRemover),
        pretend.call(HostRewrite),
    ]
    assert configurator_obj.include.calls == (
        [
            pretend.call("pyramid_services"),
            pretend.call(".metrics"),
            pretend.call(".csrf"),
        ]
        + [
            pretend.call(x)
            for x in [
                (
                    "pyramid_debugtoolbar"
                    if environment == config.Environment.development
                    else None
                )
            ]
            if x is not None
        ]
        + [
            pretend.call(".logging"),
            pretend.call("pyramid_jinja2"),
            pretend.call(".filters"),
            pretend.call("pyramid_mailer"),
            pretend.call("pyramid_retry"),
            pretend.call("pyramid_tm"),
            pretend.call(".legacy.api.xmlrpc"),
            pretend.call(".legacy.api.xmlrpc.cache"),
            pretend.call("pyramid_rpc.xmlrpc"),
            pretend.call(".legacy.action_routing"),
            pretend.call(".domain"),
            pretend.call(".i18n"),
            pretend.call(".db"),
            pretend.call(".tasks"),
            pretend.call(".rate_limiting"),
            pretend.call(".static"),
            pretend.call(".policy"),
            pretend.call(".search"),
            pretend.call(".aws"),
            pretend.call(".gcloud"),
            pretend.call(".sessions"),
            pretend.call(".cache.http"),
            pretend.call(".cache.origin"),
            pretend.call(".email"),
            pretend.call(".accounts"),
            pretend.call(".macaroons"),
            pretend.call(".malware"),
            pretend.call(".manage"),
            pretend.call(".packaging"),
            pretend.call(".tuf"),
            pretend.call(".redirects"),
            pretend.call(".routes"),
            pretend.call(".admin"),
            pretend.call(".forklift"),
            pretend.call(".sentry"),
            pretend.call(".csp"),
            pretend.call(".referrer_policy"),
            pretend.call(".http"),
        ]
        + [pretend.call(x) for x in [configurator_settings.get("warehouse.theme")] if x]
        + [pretend.call(".sanity")]
    )
    assert configurator_obj.add_jinja2_renderer.calls == [
        pretend.call(".html"),
        pretend.call(".txt"),
        pretend.call(".xml"),
    ]
    assert configurator_obj.add_jinja2_search_path.calls == [
        pretend.call("warehouse:templates", name=".html"),
        pretend.call("warehouse:templates", name=".txt"),
        pretend.call("warehouse:templates", name=".xml"),
    ]
    assert configurator_obj.add_settings.calls == [
        pretend.call({"jinja2.newstyle": True}),
        pretend.call({"jinja2.i18n.domain": "messages"}),
        pretend.call({"retry.attempts": 3}),
        pretend.call(
            {
                "tm.manager_hook": mock.ANY,
                "tm.activate_hook": config.activate_hook,
                "tm.commit_veto": config.commit_veto,
                "tm.annotate_user": False,
            }
        ),
        pretend.call({"http": {"verify": "/etc/ssl/certs/"}}),
    ]
    add_settings_dict = configurator_obj.add_settings.calls[3].args[0]
    assert add_settings_dict["tm.manager_hook"](pretend.stub()) is transaction_manager
    assert configurator_obj.add_tween.calls == [
        pretend.call("warehouse.config.require_https_tween_factory"),
        pretend.call(
            "warehouse.utils.compression.compression_tween_factory",
            over=[
                "warehouse.cache.http.conditional_http_tween_factory",
                "pyramid_debugtoolbar.toolbar_tween_factory",
                EXCVIEW,
            ],
        ),
    ]
    assert configurator_obj.add_static_view.calls == [
        pretend.call("tuf", "warehouse:tuf/dist/metadata.staged/"),
        pretend.call("static", "warehouse:static/dist/", cache_max_age=315360000),
    ]
    assert configurator_obj.add_cache_buster.calls == [
        pretend.call("warehouse:static/dist/", cachebuster_obj)
    ]
    assert cachebuster_cls.calls == [
        pretend.call("warehouse:static/dist/manifest.json", reload=False, strict=True)
    ]
    assert configurator_obj.whitenoise_serve_static.calls == [
        pretend.call(autorefresh=False, max_age=315360000)
    ]
    assert configurator_obj.whitenoise_add_files.calls == [
        pretend.call("warehouse:static/dist/", prefix="/static/")
    ]
    assert configurator_obj.whitenoise_add_manifest.calls == [
        pretend.call("warehouse:static/dist/manifest.json", prefix="/static/")
    ]
    assert configurator_obj.add_directive.calls == [
        pretend.call("add_template_view", config.template_view, action_wrap=False)
    ]
    assert configurator_obj.scan.calls == [
        pretend.call(
            ignore=["warehouse.migrations.env", "warehouse.celery", "warehouse.wsgi"]
        )
    ]
    assert configurator_obj.commit.calls == [pretend.call()]
    assert configurator_obj.add_renderer.calls == [
        pretend.call("json", json_renderer_obj),
        pretend.call("xmlrpc", xmlrpc_renderer_obj),
    ]

    assert json_renderer_cls.calls == [
        pretend.call(sort_keys=True, separators=(",", ":"))
    ]

    assert xmlrpc_renderer_cls.calls == [pretend.call(allow_none=True)]
