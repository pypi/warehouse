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

import os

from datetime import timedelta
from unittest import mock

import orjson
import pretend
import pytest

from pyramid import renderers
from pyramid.authorization import Allow, Authenticated
from pyramid.tweens import EXCVIEW

from warehouse import config
from warehouse.authnz import Permissions
from warehouse.utils.wsgi import ProxyFixer, VhmRootRemover


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
    ("settings", "environment"),
    [
        (None, config.Environment.production),
        ({}, config.Environment.production),
        ({"my settings": "the settings value"}, config.Environment.production),
        (None, config.Environment.development),
        ({}, config.Environment.development),
        ({"my settings": "the settings value"}, config.Environment.development),
    ],
)
def test_configure(monkeypatch, settings, environment):
    json_renderer_obj = pretend.stub()
    json_renderer_cls = pretend.call_recorder(lambda **kw: json_renderer_obj)
    monkeypatch.setattr(renderers, "JSON", json_renderer_cls)

    xmlrpc_renderer_obj = pretend.stub()
    xmlrpc_renderer_cls = pretend.call_recorder(lambda **kw: xmlrpc_renderer_obj)
    monkeypatch.setattr(config, "XMLRPCRenderer", xmlrpc_renderer_cls)

    # Ignore all environment variables in the test environment, except for WAREHOUSE_ENV
    monkeypatch.setattr(
        os,
        "environ",
        {
            "WAREHOUSE_ENV": {
                config.Environment.development: "development",
                config.Environment.production: "production",
            }[environment],
            "GCLOUD_SERVICE_JSON": "e30=",
        },
    )

    class FakeRegistry(dict):
        def __init__(self):
            self.settings = {
                "warehouse.token": "insecure token",
                "warehouse.ip_salt": "insecure salt",
                "warehouse.env": environment,
                "camo.url": "http://camo.example.com/",
                "pyramid.reload_assets": False,
                "dirs.packages": "/srv/data/pypi/packages/",
                "warehouse.xmlrpc.client.ratelimit_string": "3600 per hour",
            }

    configurator_settings = dict()
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
        scan=pretend.call_recorder(lambda categories, ignore: None),
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

    result = config.configure(settings=settings.copy() if settings else None)

    expected_settings = {
        "warehouse.env": environment,
        "warehouse.commit": "null",
        "site.name": "Warehouse",
        "token.two_factor.max_age": 300,
        "remember_device.days": 30,
        "remember_device.seconds": timedelta(days=30).total_seconds(),
        "token.remember_device.max_age": timedelta(days=30).total_seconds(),
        "token.default.max_age": 21600,
        "pythondotorg.host": "https://www.python.org",
        "warehouse.xmlrpc.client.ratelimit_string": "3600 per hour",
        "warehouse.xmlrpc.search.enabled": True,
        "github.token_scanning_meta_api.url": (
            "https://api.github.com/meta/public_keys/token_scanning"
        ),
        "warehouse.account.user_login_ratelimit_string": "10 per 5 minutes",
        "warehouse.account.ip_login_ratelimit_string": "10 per 5 minutes",
        "warehouse.account.global_login_ratelimit_string": "1000 per 5 minutes",
        "warehouse.account.email_add_ratelimit_string": "2 per day",
        "warehouse.account.verify_email_ratelimit_string": "3 per 6 hours",
        "warehouse.account.accounts_search_ratelimit_string": "100 per hour",
        "warehouse.account.password_reset_ratelimit_string": "5 per day",
        "warehouse.manage.oidc.user_registration_ratelimit_string": "100 per day",
        "warehouse.manage.oidc.ip_registration_ratelimit_string": "100 per day",
        "warehouse.packaging.project_create_user_ratelimit_string": "20 per hour",
        "warehouse.packaging.project_create_ip_ratelimit_string": "40 per hour",
        "oidc.backend": "warehouse.oidc.services.OIDCPublisherService",
        "warehouse.organizations.max_undecided_organization_applications": 3,
        "reconcile_file_storages.batch_size": 100,
        "metadata_backfill.batch_size": 500,
        "gcloud.service_account_info": {},
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
                "livereload.url": "http://localhost:35729",
            }
        )

    if settings is not None:
        expected_settings.update(settings)

    assert configurator_cls.calls == [pretend.call(settings=expected_settings)]
    assert result is configurator_obj
    assert configurator_obj.set_root_factory.calls == [pretend.call(config.RootFactory)]
    assert configurator_obj.add_wsgi_middleware.calls == [
        pretend.call(
            ProxyFixer, token="insecure token", ip_salt="insecure salt", num_proxies=1
        ),
        pretend.call(VhmRootRemover),
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
            pretend.call(".predicates"),
            pretend.call(".i18n"),
            pretend.call(".db"),
            pretend.call(".tasks"),
            pretend.call(".rate_limiting"),
            pretend.call(".static"),
            pretend.call(".search"),
            pretend.call(".aws"),
            pretend.call(".b2"),
            pretend.call(".gcloud"),
            pretend.call(".sessions"),
            pretend.call(".cache.http"),
            pretend.call(".cache.origin"),
            pretend.call(".email"),
            pretend.call(".accounts"),
            pretend.call(".macaroons"),
            pretend.call(".oidc"),
            pretend.call(".manage"),
            pretend.call(".organizations"),
            pretend.call(".subscriptions"),
            pretend.call(".packaging"),
            pretend.call(".redirects"),
            pretend.call("pyramid_redirect"),
            pretend.call(".routes"),
            pretend.call(".sponsors"),
            pretend.call(".banners"),
            pretend.call(".admin"),
            pretend.call(".forklift"),
            pretend.call(".api.config"),
            pretend.call(".utils.wsgi"),
            pretend.call(".sentry"),
            pretend.call(".csp"),
            pretend.call(".referrer_policy"),
            pretend.call(".captcha"),
            pretend.call(".http"),
            pretend.call(".utils.row_counter"),
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
        pretend.call({"jinja2.lstrip_blocks": True}),
        pretend.call({"jinja2.trim_blocks": True}),
        pretend.call({"retry.attempts": 3}),
        pretend.call(
            {
                "tm.manager_hook": mock.ANY,
                "tm.activate_hook": config.activate_hook,
                "tm.annotate_user": False,
            }
        ),
        pretend.call({"pyramid_redirect.structlog": True}),
        pretend.call({"http": {"verify": "/etc/ssl/certs/"}}),
    ]
    add_settings_dict = configurator_obj.add_settings.calls[5].args[0]
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
        pretend.call("static", "warehouse:static/dist/", cache_max_age=315360000)
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
            categories=(
                "pyramid",
                "warehouse",
            ),
            ignore=["warehouse.migrations.env", "warehouse.celery", "warehouse.wsgi"],
        )
    ]
    assert configurator_obj.commit.calls == [pretend.call()]
    assert configurator_obj.add_renderer.calls == [
        pretend.call("json", json_renderer_obj),
        pretend.call("xmlrpc", xmlrpc_renderer_obj),
    ]

    assert json_renderer_cls.calls == [
        pretend.call(
            serializer=orjson.dumps,
            option=orjson.OPT_SORT_KEYS | orjson.OPT_APPEND_NEWLINE,
        )
    ]

    assert xmlrpc_renderer_cls.calls == [pretend.call(allow_none=True)]


def test_root_factory_access_control_list():
    acl = config.RootFactory.__acl__

    assert acl == [
        (
            Allow,
            "group:admins",
            (
                Permissions.AdminBannerRead,
                Permissions.AdminBannerWrite,
                Permissions.AdminDashboardRead,
                Permissions.AdminDashboardSidebarRead,
                Permissions.AdminEmailsRead,
                Permissions.AdminEmailsWrite,
                Permissions.AdminFlagsRead,
                Permissions.AdminFlagsWrite,
                Permissions.AdminIpAddressesRead,
                Permissions.AdminJournalRead,
                Permissions.AdminMacaroonsRead,
                Permissions.AdminMacaroonsWrite,
                Permissions.AdminObservationsRead,
                Permissions.AdminObservationsWrite,
                Permissions.AdminOrganizationsRead,
                Permissions.AdminOrganizationsWrite,
                Permissions.AdminProhibitedProjectsRead,
                Permissions.AdminProhibitedProjectsWrite,
                Permissions.AdminProjectsDelete,
                Permissions.AdminProjectsRead,
                Permissions.AdminProjectsSetLimit,
                Permissions.AdminProjectsWrite,
                Permissions.AdminRoleAdd,
                Permissions.AdminRoleDelete,
                Permissions.AdminSponsorsRead,
                Permissions.AdminUsersRead,
                Permissions.AdminUsersWrite,
            ),
        ),
        (
            Allow,
            "group:moderators",
            (
                Permissions.AdminBannerRead,
                Permissions.AdminDashboardRead,
                Permissions.AdminDashboardSidebarRead,
                Permissions.AdminEmailsRead,
                Permissions.AdminFlagsRead,
                Permissions.AdminJournalRead,
                Permissions.AdminObservationsRead,
                Permissions.AdminObservationsWrite,
                Permissions.AdminOrganizationsRead,
                Permissions.AdminProhibitedProjectsRead,
                Permissions.AdminProjectsRead,
                Permissions.AdminProjectsSetLimit,
                Permissions.AdminRoleAdd,
                Permissions.AdminRoleDelete,
                Permissions.AdminSponsorsRead,
                Permissions.AdminUsersRead,
            ),
        ),
        (
            Allow,
            "group:psf_staff",
            (
                Permissions.AdminBannerRead,
                Permissions.AdminBannerWrite,
                Permissions.AdminDashboardRead,
                Permissions.AdminSponsorsRead,
                Permissions.AdminSponsorsWrite,
            ),
        ),
        (
            Allow,
            "group:observers",
            (
                Permissions.APIEcho,
                Permissions.APIObservationsAdd,
            ),
        ),
        (
            Allow,
            Authenticated,
            (
                Permissions.Account2FA,
                Permissions.AccountAPITokens,
                Permissions.AccountManage,
                Permissions.AccountManagePublishing,
                Permissions.AccountVerifyEmail,
                Permissions.AccountVerifyOrgRole,
                Permissions.AccountVerifyProjectRole,
                Permissions.OrganizationsManage,
                Permissions.ProjectsRead,
            ),
        ),
    ]
