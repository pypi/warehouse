# SPDX-License-Identifier: Apache-2.0

import os
import types

from datetime import timedelta

import orjson
import pytest

from pyramid import renderers
from pyramid.authorization import Allow, Authenticated
from pyramid.tweens import EXCVIEW

from warehouse import config
from warehouse.authnz import Permissions
from warehouse.utils.wsgi import ProxyFixer, VhmRootRemover


class TestRequireHTTPSTween:
    def test_noops_when_disabled(self, mocker):
        registry = mocker.Mock()
        registry.settings.get.return_value = False

        assert (
            config.require_https_tween_factory(mocker.sentinel.handler, registry)
            is mocker.sentinel.handler
        )
        registry.settings.get.assert_called_once_with("enforce_https", True)

    @pytest.mark.parametrize(
        ("params", "scheme"),
        [({}, "https"), ({":action": "thing"}, "https"), ({}, "http")],
    )
    def test_allows_through(self, params, scheme, pyramid_request, mocker):
        pyramid_request.params = params
        pyramid_request.scheme = scheme
        handler = mocker.Mock(return_value=mocker.sentinel.response)
        registry = types.SimpleNamespace(settings={"enforce_https": True})

        tween = config.require_https_tween_factory(handler, registry)

        assert tween(pyramid_request) is mocker.sentinel.response
        handler.assert_called_once_with(pyramid_request)

    @pytest.mark.parametrize(("params", "scheme"), [({":action": "thing"}, "http")])
    def test_rejects(self, params, scheme, pyramid_request, mocker):
        pyramid_request.params = params
        pyramid_request.scheme = scheme
        registry = types.SimpleNamespace(settings={"enforce_https": True})

        tween = config.require_https_tween_factory(mocker.sentinel.handler, registry)
        resp = tween(pyramid_request)

        assert resp.status == "403 SSL is required"
        assert resp.headers["X-Fastly-Error"] == "803"
        assert resp.content_type == "text/plain"
        assert resp.body == b"SSL is required."


@pytest.mark.parametrize(
    ("path", "expected"),
    [("/foo/bar/", True), ("/static/wat/", False), ("/_debug_toolbar/thing/", False)],
)
def test_activate_hook(path, expected, pyramid_request):
    pyramid_request.path = path
    assert config.activate_hook(pyramid_request) == expected


@pytest.mark.parametrize("route_kw", [None, {}, {"foo": "bar"}])
def test_template_view(route_kw, mocker):
    configobj = mocker.Mock(spec=["add_route", "add_view"])

    config.template_view(configobj, "test", "/test/", "test.html", route_kw=route_kw)

    assert configobj.add_route.call_args_list == [
        mocker.call("test", "/test/", **({} if route_kw is None else route_kw))
    ]
    assert configobj.add_view.call_args_list == [
        mocker.call(renderer="test.html", route_name="test")
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
    ("environ", "coercer", "default", "db", "expected"),
    [
        (
            {"REDIS_URL": "redis://127.0.0.1:6379"},
            None,
            None,
            None,
            {"test.foo": "redis://127.0.0.1:6379/0"},
        ),
        (
            {"REDIS_URL": "redis://127.0.0.1:6379"},
            None,
            None,
            0,
            {"test.foo": "redis://127.0.0.1:6379/0"},
        ),
        (
            {"REDIS_URL": "redis://127.0.0.1:6379"},
            None,
            None,
            1,
            {"test.foo": "redis://127.0.0.1:6379/1"},
        ),
        ({}, None, None, None, {}),
        ({}, None, None, 0, {}),
        ({}, None, None, 1, {}),
        (
            {"REDIS_URL": "redis://127.0.0.1:6379"},
            str,
            None,
            None,
            {"test.foo": "redis://127.0.0.1:6379/0"},
        ),
        (
            {"REDIS_URL": "redis://127.0.0.1:6379"},
            str,
            None,
            0,
            {"test.foo": "redis://127.0.0.1:6379/0"},
        ),
        (
            {"REDIS_URL": "redis://127.0.0.1:6379"},
            str,
            None,
            1,
            {"test.foo": "redis://127.0.0.1:6379/1"},
        ),
        ({}, str, None, None, {}),
        ({}, str, None, 0, {}),
        (
            {},
            str,
            "redis://127.0.0.1:6379/6",
            1,
            {"test.foo": "redis://127.0.0.1:6379/6"},
        ),
        (
            {"REDIS_URL": "redis://127.0.0.1:6379/6"},
            str,
            None,
            9,
            {"test.foo": "redis://127.0.0.1:6379/9"},
        ),
        (
            {"REDIS_URL": "rediss://foo:bar@example.com:6379/6?fizz=buzz&wu=tang"},
            str,
            None,
            9,
            {"test.foo": "rediss://foo:bar@example.com:6379/9?fizz=buzz&wu=tang"},
        ),
    ],
)
def test_maybe_set_redis(monkeypatch, environ, coercer, default, db, expected):
    for key, value in environ.items():
        monkeypatch.setenv(key, value)
    settings = {}
    config.maybe_set_redis(
        settings, "test.foo", "REDIS_URL", coercer=coercer, default=default, db=db
    )
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
def test_configure(monkeypatch, mocker, settings, environment):
    json_renderer_cls = mocker.patch.object(
        renderers, "JSON", return_value=mocker.sentinel.json_renderer_obj
    )

    xmlrpc_renderer_cls = mocker.patch.object(
        config, "XMLRPCRenderer", return_value=mocker.sentinel.xmlrpc_renderer_obj
    )

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

    configurator_settings = {}
    configurator_obj = mocker.Mock(
        spec=[
            "registry",
            "set_root_factory",
            "include",
            "add_directive",
            "add_wsgi_middleware",
            "add_renderer",
            "add_request_method",
            "add_jinja2_renderer",
            "add_jinja2_search_path",
            "get_settings",
            "add_settings",
            "add_tween",
            "add_static_view",
            "add_cache_buster",
            "whitenoise_serve_static",
            "whitenoise_add_files",
            "whitenoise_add_manifest",
            "scan",
            "commit",
            "add_view_deriver",
        ]
    )
    configurator_obj.registry = FakeRegistry()
    configurator_obj.get_settings.return_value = configurator_settings
    configurator_obj.add_settings.side_effect = configurator_settings.update
    configurator_cls = mocker.patch.object(
        config, "Configurator", return_value=configurator_obj
    )

    cachebuster_cls = mocker.patch.object(
        config, "ManifestCacheBuster", return_value=mocker.sentinel.cachebuster_obj
    )

    transaction = mocker.patch.object(config, "transaction")
    transaction.TransactionManager.return_value = mocker.sentinel.transaction_manager

    result = config.configure(settings=settings.copy() if settings else None)

    expected_settings = {
        "warehouse.env": environment,
        "terms.revision": "initial",
        "terms.notification_batch_size": 1000,
        "warehouse.commit": "null",
        "userdocs.domain": "https://docs.pypi.org",
        "site.name": "Warehouse",
        "token.two_factor.max_age": 300,
        "remember_device.days": 30,
        "remember_device.seconds": timedelta(days=30).total_seconds(),
        "token.remember_device.max_age": timedelta(days=30).total_seconds(),
        "token.default.max_age": 21600,
        "pythondotorg.host": "https://www.python.org",
        "warehouse.xmlrpc.client.ratelimit_string": "3600 per hour",
        "github.token_scanning_meta_api.url": (
            "https://api.github.com/meta/public_keys/token_scanning"
        ),
        "warehouse.account.user_login_ratelimit_string": "10 per 5 minutes",
        "warehouse.account.ip_login_ratelimit_string": "10 per 5 minutes",
        "warehouse.account.global_login_ratelimit_string": "1000 per 5 minutes",
        "warehouse.account.2fa_user_ratelimit_string": "5 per 5 minutes, 20 per hour, 50 per day",  # noqa: E501
        "warehouse.account.2fa_ip_ratelimit_string": "10 per 5 minutes, 50 per hour",
        "warehouse.account.email_add_ratelimit_string": "2 per day",
        "warehouse.account.verify_email_ratelimit_string": "3 per 6 hours",
        "warehouse.account.accounts_search_ratelimit_string": "100 per hour",
        "warehouse.account.password_reset_ratelimit_string": "5 per day",
        "warehouse.manage.oidc.user_registration_ratelimit_string": "100 per day",
        "warehouse.manage.oidc.ip_registration_ratelimit_string": "100 per day",
        "warehouse.packaging.project_create_user_ratelimit_string": "20 per hour",
        "warehouse.packaging.project_create_ip_ratelimit_string": "40 per hour",
        "warehouse.packaging.project_create_organization_ratelimit_string": (
            "20 per hour"
        ),
        "warehouse.search.ratelimit_string": "5 per second",
        "oidc.backend": "warehouse.oidc.services.OIDCPublisherService",
        "integrity.backend": "warehouse.attestations.services.IntegrityService",
        "warehouse.organizations.max_undecided_organization_applications": 3,
        "reconcile_file_storages.batch_size": 100,
        "gcloud.service_account_info": {},
        "warehouse.forklift.legacy.MAX_FILESIZE_MIB": 100,
        "warehouse.forklift.legacy.MAX_PROJECT_SIZE_GIB": 10,
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
                    ("pyramid_debugtoolbar.panels.request_vars.RequestVarsDebugPanel"),
                    "pyramid_debugtoolbar.panels.renderings.RenderingsDebugPanel",
                    "pyramid_debugtoolbar.panels.session.SessionDebugPanel",
                    "pyramid_debugtoolbar.panels.logger.LoggingPanel",
                    ("pyramid_debugtoolbar.panels.performance.PerformanceDebugPanel"),
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

    assert configurator_cls.call_args_list == [mocker.call(settings=expected_settings)]
    assert result is configurator_obj
    assert configurator_obj.set_root_factory.call_args_list == [
        mocker.call(config.RootFactory)
    ]
    assert configurator_obj.add_wsgi_middleware.call_args_list == [
        mocker.call(
            ProxyFixer, token="insecure token", ip_salt="insecure salt", num_proxies=1
        ),
        mocker.call(VhmRootRemover),
    ]
    assert configurator_obj.include.call_args_list == (
        [
            mocker.call("pyramid_services"),
            mocker.call(".metrics"),
            mocker.call(".csrf"),
        ]
        + [
            mocker.call(x)
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
            mocker.call(".logging"),
            mocker.call("pyramid_jinja2"),
            mocker.call(".filters"),
            mocker.call("pyramid_mailer"),
            mocker.call("pyramid_retry"),
            mocker.call("pyramid_tm"),
            mocker.call(".rate_limiting"),
            mocker.call(".legacy.api.xmlrpc"),
            mocker.call(".legacy.api.xmlrpc.cache"),
            mocker.call("pyramid_rpc.xmlrpc"),
            mocker.call(".legacy.action_routing"),
            mocker.call(".predicates"),
            mocker.call(".i18n"),
            mocker.call(".db"),
            mocker.call(".tasks"),
            mocker.call(".static"),
            mocker.call(".search"),
            mocker.call(".aws"),
            mocker.call(".b2"),
            mocker.call(".gcloud"),
            mocker.call(".sessions"),
            mocker.call(".cache.http"),
            mocker.call(".cache.origin"),
            mocker.call(".cache"),
            mocker.call(".email"),
            mocker.call(".accounts"),
            mocker.call(".macaroons"),
            mocker.call(".oidc"),
            mocker.call(".attestations"),
            mocker.call(".manage"),
            mocker.call(".organizations"),
            mocker.call(".subscriptions"),
            mocker.call(".packaging"),
            mocker.call(".redirects"),
            mocker.call("pyramid_redirect"),
            mocker.call(".routes"),
            mocker.call(".sponsors"),
            mocker.call(".banners"),
            mocker.call(".admin"),
            mocker.call(".forklift"),
            mocker.call(".api.config"),
            mocker.call(".utils.wsgi"),
            mocker.call(".sentry"),
            mocker.call(".csp"),
            mocker.call(".referrer_policy"),
            mocker.call(".captcha"),
            mocker.call(".helpdesk"),
            mocker.call(".http"),
            mocker.call(".utils.row_counter"),
        ]
        + [mocker.call(x) for x in [configurator_settings.get("warehouse.theme")] if x]
        + [mocker.call(".sanity")]
    )
    assert configurator_obj.add_jinja2_renderer.call_args_list == [
        mocker.call(".html"),
        mocker.call(".txt"),
        mocker.call(".xml"),
    ]
    assert configurator_obj.add_jinja2_search_path.call_args_list == [
        mocker.call("warehouse:templates", name=".html"),
        mocker.call("warehouse:templates", name=".txt"),
        mocker.call("warehouse:templates", name=".xml"),
    ]
    assert configurator_obj.add_settings.call_args_list == [
        mocker.call({"jinja2.newstyle": True}),
        mocker.call({"jinja2.i18n.domain": "messages"}),
        mocker.call({"jinja2.lstrip_blocks": True}),
        mocker.call({"jinja2.trim_blocks": True}),
        mocker.call({"retry.attempts": 3}),
        mocker.call(
            {
                "tm.manager_hook": mocker.ANY,
                "tm.activate_hook": config.activate_hook,
                "tm.annotate_user": False,
            }
        ),
        mocker.call({"pyramid_redirect.structlog": True}),
        mocker.call({"http": {"verify": "/etc/ssl/certs/"}}),
    ]
    add_settings_dict = configurator_obj.add_settings.call_args_list[5].args[0]
    assert (
        add_settings_dict["tm.manager_hook"](mocker.sentinel.request)
        is mocker.sentinel.transaction_manager
    )
    assert configurator_obj.add_tween.call_args_list == [
        mocker.call("warehouse.config.require_https_tween_factory"),
        mocker.call(
            "warehouse.utils.compression.compression_tween_factory",
            over=[
                "warehouse.cache.http.conditional_http_tween_factory",
                "pyramid_debugtoolbar.toolbar_tween_factory",
                EXCVIEW,
            ],
        ),
    ]
    assert configurator_obj.add_static_view.call_args_list == [
        mocker.call("static", "warehouse:static/dist/", cache_max_age=315360000)
    ]
    assert configurator_obj.add_cache_buster.call_args_list == [
        mocker.call("warehouse:static/dist/", mocker.sentinel.cachebuster_obj)
    ]
    assert cachebuster_cls.call_args_list == [
        mocker.call("warehouse:static/dist/manifest.json", reload=False, strict=True)
    ]
    assert configurator_obj.whitenoise_serve_static.call_args_list == [
        mocker.call(autorefresh=False, max_age=315360000)
    ]
    assert configurator_obj.whitenoise_add_files.call_args_list == [
        mocker.call("warehouse:static/dist/", prefix="/static/")
    ]
    assert configurator_obj.whitenoise_add_manifest.call_args_list == [
        mocker.call("warehouse:static/dist/manifest.json", prefix="/static/")
    ]
    assert configurator_obj.add_directive.call_args_list == [
        mocker.call("add_template_view", config.template_view, action_wrap=False)
    ]
    assert configurator_obj.scan.call_args_list == [
        mocker.call(
            categories=(
                "pyramid",
                "warehouse",
            ),
            ignore=["warehouse.migrations.env", "warehouse.celery", "warehouse.wsgi"],
        )
    ]
    assert configurator_obj.commit.call_args_list == [mocker.call()]
    assert configurator_obj.add_renderer.call_args_list == [
        mocker.call("json", mocker.sentinel.json_renderer_obj),
        mocker.call("xmlrpc", mocker.sentinel.xmlrpc_renderer_obj),
    ]
    assert configurator_obj.add_view_deriver.call_args_list == [
        mocker.call(
            config.reject_duplicate_post_keys_view,
            over="rendered_view",
            under="decorated_view",
        )
    ]

    assert json_renderer_cls.call_args_list == [
        mocker.call(
            serializer=orjson.dumps,
            option=orjson.OPT_SORT_KEYS | orjson.OPT_APPEND_NEWLINE,
        )
    ]

    assert xmlrpc_renderer_cls.call_args_list == [mocker.call(allow_none=True)]


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
                Permissions.AdminIpAddressesWrite,
                Permissions.AdminJournalRead,
                Permissions.AdminMacaroonsInspect,
                Permissions.AdminMacaroonsRead,
                Permissions.AdminMacaroonsWrite,
                Permissions.AdminObservationsRead,
                Permissions.AdminObservationsWrite,
                Permissions.AdminOrganizationsRead,
                Permissions.AdminOrganizationsSetLimit,
                Permissions.AdminOrganizationsWrite,
                Permissions.AdminOrganizationsNameWrite,
                Permissions.AdminProhibitedEmailDomainsRead,
                Permissions.AdminProhibitedEmailDomainsWrite,
                Permissions.AdminProhibitedProjectsRead,
                Permissions.AdminProhibitedProjectsWrite,
                Permissions.AdminProhibitedProjectsRelease,
                Permissions.AdminProhibitedProjectsUltranormRelease,
                Permissions.AdminProhibitedUsernameRead,
                Permissions.AdminProhibitedUsernameWrite,
                Permissions.AdminProjectsDelete,
                Permissions.AdminProjectsRead,
                Permissions.AdminProjectsSetLimit,
                Permissions.AdminProjectsWrite,
                Permissions.AdminRoleAdd,
                Permissions.AdminRoleDelete,
                Permissions.AdminRoleUpdate,
                Permissions.AdminSponsorsRead,
                Permissions.AdminUsersRead,
                Permissions.AdminUsersWrite,
                Permissions.AdminUsersEmailWrite,
                Permissions.AdminUsersAccountRecoveryWrite,
                Permissions.AdminUsersRecoveryCodesBurn,
                Permissions.AdminVulnerabilitiesRead,
                Permissions.AdminVulnerabilitiesWrite,
            ),
        ),
        (
            Allow,
            "group:support",
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
                Permissions.AdminOrganizationsSetLimit,
                Permissions.AdminOrganizationsWrite,
                Permissions.AdminOrganizationsNameWrite,
                Permissions.AdminProhibitedEmailDomainsRead,
                Permissions.AdminProhibitedProjectsRead,
                Permissions.AdminProhibitedProjectsRelease,
                Permissions.AdminProhibitedProjectsUltranormRelease,
                Permissions.AdminProhibitedUsernameRead,
                Permissions.AdminProjectsRead,
                Permissions.AdminProjectsSetLimit,
                Permissions.AdminRoleAdd,
                Permissions.AdminRoleDelete,
                Permissions.AdminRoleUpdate,
                Permissions.AdminSponsorsRead,
                Permissions.AdminUsersRead,
                Permissions.AdminUsersEmailWrite,
                Permissions.AdminUsersAccountRecoveryWrite,
                Permissions.AdminUsersRecoveryCodesBurn,
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
                Permissions.AdminProhibitedEmailDomainsRead,
                Permissions.AdminProhibitedProjectsRead,
                Permissions.AdminProhibitedUsernameRead,
                Permissions.AdminProjectsRead,
                Permissions.AdminProjectsSetLimit,
                Permissions.AdminRoleAdd,
                Permissions.AdminRoleDelete,
                Permissions.AdminRoleUpdate,
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
