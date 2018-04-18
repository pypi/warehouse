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

import enum
import os
import shlex
import urllib.parse

import transaction

from pyramid import renderers
from pyramid.config import Configurator as _Configurator
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.response import Response
from pyramid.security import Allow
from pyramid.tweens import EXCVIEW
from pyramid_rpc.xmlrpc import XMLRPCRenderer

from warehouse import __commit__
from warehouse.utils.static import ManifestCacheBuster
from warehouse.utils.wsgi import ProxyFixer, VhmRootRemover, HostRewrite


class Environment(enum.Enum):
    production = "production"
    development = "development"


class Configurator(_Configurator):

    def add_wsgi_middleware(self, middleware, *args, **kwargs):
        middlewares = self.get_settings().setdefault("wsgi.middlewares", [])
        middlewares.append((middleware, args, kwargs))

    def make_wsgi_app(self, *args, **kwargs):
        # Get the WSGI application from the underlying configurator
        app = super().make_wsgi_app(*args, **kwargs)

        # Look to see if we have any WSGI middlewares configured.
        for middleware, args, kw in self.get_settings()["wsgi.middlewares"]:
            app = middleware(app, *args, **kw)

        # Finally, return our now wrapped app
        return app


class RootFactory:

    __parent__ = None
    __name__ = None

    __acl__ = [
        (Allow, "group:admins", "admin"),
    ]

    def __init__(self, request):
        pass


def junk_encoding_tween_factory(handler, request):

    def junk_encoding_tween(request):
        # We're going to test our request a bit, before we pass it into the
        # handler. This will let us return a better error than a 500 if we
        # can't decode these.

        # Ref: https://github.com/Pylons/webob/issues/161
        # Ref: https://github.com/Pylons/webob/issues/115
        try:
            request.GET.get("", None)
        except UnicodeDecodeError:
            return HTTPBadRequest("Invalid bytes in query string.")

        # Look for invalid bytes in a path.
        try:
            request.path_info
        except UnicodeDecodeError:
            return HTTPBadRequest("Invalid bytes in URL.")

        # Everything worked! Handle this request as normal.
        return handler(request)

    return junk_encoding_tween


def unicode_redirect_tween_factory(handler, request):

    def unicode_redirect_tween(request):
        response = handler(request)
        if response.location:
            try:
                response.location.encode('ascii')
            except UnicodeEncodeError:
                response.location = '/'.join(
                    [urllib.parse.quote_plus(x)
                     for x in response.location.split('/')])

        return response

    return unicode_redirect_tween


def require_https_tween_factory(handler, registry):

    if not registry.settings.get("enforce_https", True):
        return handler

    def require_https_tween(request):
        # If we have an :action URL and we're not using HTTPS, then we want to
        # return a 403 error.
        if request.params.get(":action", None) and request.scheme != "https":
            resp = Response(
                "SSL is required.",
                status=403,
                content_type="text/plain",
            )
            resp.status = "403 SSL is required"
            resp.headers["X-Fastly-Error"] = "803"
            return resp

        return handler(request)

    return require_https_tween


def activate_hook(request):
    if request.path.startswith(("/_debug_toolbar/", "/static/")):
        return False
    return True


def template_view(config, name, route, template, route_kw=None):
    if route_kw is None:
        route_kw = {}

    config.add_route(name, route, **route_kw)
    config.add_view(renderer=template, route_name=name)


def maybe_set(settings, name, envvar, coercer=None, default=None):
    if envvar in os.environ:
        value = os.environ[envvar]
        if coercer is not None:
            value = coercer(value)
        settings.setdefault(name, value)
    elif default is not None:
        settings.setdefault(name, default)


def maybe_set_compound(settings, base, name, envvar):
    if envvar in os.environ:
        value = shlex.split(os.environ[envvar])
        kwargs = {k: v for k, v in (i.split("=") for i in value[1:])}
        settings[".".join([base, name])] = value[0]
        for key, value in kwargs.items():
            settings[".".join([base, key])] = value


def configure(settings=None):
    if settings is None:
        settings = {}

    # Add information about the current copy of the code.
    settings.setdefault("warehouse.commit", __commit__)

    # Set the environment from an environment variable, if one hasn't already
    # been set.
    maybe_set(
        settings, "warehouse.env", "WAREHOUSE_ENV", Environment,
        default=Environment.production,
    )

    # Pull in default configuration from the environment.
    maybe_set(settings, "warehouse.token", "WAREHOUSE_TOKEN")
    maybe_set(settings, "warehouse.num_proxies", "WAREHOUSE_NUM_PROXIES", int)
    maybe_set(settings, "warehouse.theme", "WAREHOUSE_THEME")
    maybe_set(settings, "warehouse.domain", "WAREHOUSE_DOMAIN")
    maybe_set(settings, "forklift.domain", "FORKLIFT_DOMAIN")
    maybe_set(settings, "warehouse.legacy_domain", "WAREHOUSE_LEGACY_DOMAIN")
    maybe_set(settings, "site.name", "SITE_NAME", default="Warehouse")
    maybe_set(settings, "aws.key_id", "AWS_ACCESS_KEY_ID")
    maybe_set(settings, "aws.secret_key", "AWS_SECRET_ACCESS_KEY")
    maybe_set(settings, "aws.region", "AWS_REGION")
    maybe_set(settings, "gcloud.credentials", "GCLOUD_CREDENTIALS")
    maybe_set(settings, "gcloud.project", "GCLOUD_PROJECT")
    maybe_set(settings, "warehouse.trending_table", "WAREHOUSE_TRENDING_TABLE")
    maybe_set(settings, "celery.broker_url", "AMQP_URL")
    maybe_set(settings, "celery.result_url", "REDIS_URL")
    maybe_set(settings, "celery.scheduler_url", "REDIS_URL")
    maybe_set(settings, "database.url", "DATABASE_URL")
    maybe_set(settings, "elasticsearch.url", "ELASTICSEARCH_URL")
    maybe_set(settings, "sentry.dsn", "SENTRY_DSN")
    maybe_set(settings, "sentry.transport", "SENTRY_TRANSPORT")
    maybe_set(settings, "sessions.url", "REDIS_URL")
    maybe_set(settings, "ratelimit.url", "REDIS_URL")
    maybe_set(settings, "sessions.secret", "SESSION_SECRET")
    maybe_set(settings, "camo.url", "CAMO_URL")
    maybe_set(settings, "camo.key", "CAMO_KEY")
    maybe_set(settings, "docs.url", "DOCS_URL")
    maybe_set(settings, "ga.tracking_id", "GA_TRACKING_ID")
    maybe_set(settings, "statuspage.url", "STATUSPAGE_URL")
    maybe_set(settings, "token.password.secret", "TOKEN_PASSWORD_SECRET")
    maybe_set(settings, "token.email.secret", "TOKEN_EMAIL_SECRET")
    maybe_set(settings, "warehouse.xmlrpc.cache.url", "REDIS_URL")
    maybe_set(
        settings,
        "token.password.max_age",
        "TOKEN_PASSWORD_MAX_AGE",
        coercer=int,
    )
    maybe_set(
        settings,
        "token.email.max_age",
        "TOKEN_EMAIL_MAX_AGE",
        coercer=int,
    )
    maybe_set(
        settings,
        "token.default.max_age",
        "TOKEN_DEFAULT_MAX_AGE",
        coercer=int,
        default=21600,  # 6 hours
    )
    maybe_set_compound(settings, "files", "backend", "FILES_BACKEND")
    maybe_set_compound(settings, "docs", "backend", "DOCS_BACKEND")
    maybe_set_compound(settings, "origin_cache", "backend", "ORIGIN_CACHE")
    maybe_set_compound(settings, "mail", "backend", "MAIL_BACKEND")

    # Add the settings we use when the environment is set to development.
    if settings["warehouse.env"] == Environment.development:
        settings.setdefault("enforce_https", False)
        settings.setdefault("pyramid.reload_assets", True)
        settings.setdefault("pyramid.reload_templates", True)
        settings.setdefault("pyramid.prevent_http_cache", True)
        settings.setdefault("debugtoolbar.hosts", ["0.0.0.0/0"])
        settings.setdefault(
            "debugtoolbar.panels",
            [
                ".".join(["pyramid_debugtoolbar.panels", panel])
                for panel in [
                    "versions.VersionDebugPanel",
                    "settings.SettingsDebugPanel",
                    "headers.HeaderDebugPanel",
                    "request_vars.RequestVarsDebugPanel",
                    "renderings.RenderingsDebugPanel",
                    "logger.LoggingPanel",
                    "performance.PerformanceDebugPanel",
                    "routes.RoutesDebugPanel",
                    "sqla.SQLADebugPanel",
                    "tweens.TweensDebugPanel",
                    "introspection.IntrospectionDebugPanel",
                ]
            ],
        )

    # Actually setup our Pyramid Configurator with the values pulled in from
    # the environment as well as the ones passed in to the configure function.
    config = Configurator(settings=settings)
    config.set_root_factory(RootFactory)

    # Add some fixups for some encoding/decoding issues
    config.add_tween(
        "warehouse.config.junk_encoding_tween_factory",
        over="warehouse.csp.content_security_policy_tween_factory",
    )
    config.add_tween("warehouse.config.unicode_redirect_tween_factory")

    # Register DataDog metrics
    config.include(".datadog")

    # Register our CSRF support. We do this here, immediately after we've
    # created the Configurator instance so that we ensure to get our defaults
    # set ASAP before anything else has a chance to set them and possibly call
    # Configurator().commit()
    config.include(".csrf")

    # Include anything needed by the development environment.
    if config.registry.settings["warehouse.env"] == Environment.development:
        config.include("pyramid_debugtoolbar")

    # Register our logging support
    config.include(".logging")

    # We'll want to use Jinja2 as our template system.
    config.include("pyramid_jinja2")

    # Include our filters
    config.include(".filters")

    # Including pyramid_mailer for sending emails through SMTP.
    config.include("pyramid_mailer")

    # We want to use newstyle gettext
    config.add_settings({"jinja2.newstyle": True})

    # We also want to use Jinja2 for .html templates as well, because we just
    # assume that all templates will be using Jinja.
    config.add_jinja2_renderer(".html")

    # Sometimes our files are .txt files and we still want to use Jinja2 to
    # render them.
    config.add_jinja2_renderer(".txt")

    # Anytime we want to render a .xml template, we'll also use Jinja.
    config.add_jinja2_renderer(".xml")

    # We need to enable our Client Side Include extension
    config.get_settings().setdefault(
        "jinja2.extensions",
        ["warehouse.utils.html.ClientSideIncludeExtension"],
    )

    # We'll want to configure some filters for Jinja2 as well.
    filters = config.get_settings().setdefault("jinja2.filters", {})
    filters.setdefault(
        "format_classifiers",
        "warehouse.filters:format_classifiers",
    )
    filters.setdefault("format_tags", "warehouse.filters:format_tags")
    filters.setdefault("json", "warehouse.filters:tojson")
    filters.setdefault("camoify", "warehouse.filters:camoify")
    filters.setdefault("shorten_number", "warehouse.filters:shorten_number")
    filters.setdefault("urlparse", "warehouse.filters:urlparse")
    filters.setdefault(
        "contains_valid_uris",
        "warehouse.filters:contains_valid_uris"
    )
    filters.setdefault(
        "format_package_type",
        "warehouse.filters:format_package_type"
    )
    filters.setdefault("parse_version", "warehouse.filters:parse_version")

    # We also want to register some global functions for Jinja
    jglobals = config.get_settings().setdefault("jinja2.globals", {})
    jglobals.setdefault("is_valid_uri", "warehouse.utils.http:is_valid_uri")
    jglobals.setdefault("gravatar", "warehouse.utils.gravatar:gravatar")
    jglobals.setdefault("gravatar_profile", "warehouse.utils.gravatar:profile")
    jglobals.setdefault("now", "warehouse.utils:now")

    # We'll store all of our templates in one location, warehouse/templates
    # so we'll go ahead and add that to the Jinja2 search path.
    config.add_jinja2_search_path("warehouse:templates", name=".html")
    config.add_jinja2_search_path("warehouse:templates", name=".txt")
    config.add_jinja2_search_path("warehouse:templates", name=".xml")

    # We want to configure our JSON renderer to sort the keys, and also to use
    # an ultra compact serialization format.
    config.add_renderer(
        "json",
        renderers.JSON(sort_keys=True, separators=(",", ":")),
    )

    # Configure retry support.
    config.add_settings({"retry.attempts": 3})
    config.include("pyramid_retry")

    # Configure our transaction handling so that each request gets its own
    # transaction handler and the lifetime of the transaction is tied to the
    # lifetime of the request.
    config.add_settings({
        "tm.manager_hook": lambda request: transaction.TransactionManager(),
        "tm.activate_hook": activate_hook,
        "tm.annotate_user": False,
    })
    config.include("pyramid_tm")

    # Register support for services
    config.include("pyramid_services")

    # Register our XMLRPC cache
    config.include(".legacy.api.xmlrpc.cache")

    # Register support for XMLRPC and override it's renderer to allow
    # specifying custom dumps arguments.
    config.include("pyramid_rpc.xmlrpc")
    config.add_renderer("xmlrpc", XMLRPCRenderer(allow_none=True))

    # Register support for our legacy action URLs
    config.include(".legacy.action_routing")

    # Register support for our domain predicates
    config.include(".domain")

    # Register support for template views.
    config.add_directive("add_template_view", template_view, action_wrap=False)

    # Register support for internationalization and localization
    config.include(".i18n")

    # Register the configuration for the PostgreSQL database.
    config.include(".db")

    # Register the support for Celery Tasks
    config.include(".tasks")

    # Register support for our rate limiting mechanisms
    config.include(".rate_limiting")

    config.include(".static")

    config.include(".policy")

    config.include(".search")

    # Register the support for AWS and Google Cloud
    config.include(".aws")
    config.include(".gcloud")

    # Register our session support
    config.include(".sessions")

    # Register our support for http and origin caching
    config.include(".cache.http")
    config.include(".cache.origin")

    # Register support for sendnging emails
    config.include(".email")

    # Register our authentication support.
    config.include(".accounts")

    # Register logged-in views
    config.include(".manage")

    # Allow the packaging app to register any services it has.
    config.include(".packaging")

    # Configure redirection support
    config.include(".redirects")

    # Register all our URL routes for Warehouse.
    config.include(".routes")

    # Include our admin application
    config.include(".admin")

    # Register forklift, at least until we split it out into it's own project.
    config.include(".forklift")

    # Block non HTTPS requests for the legacy ?:action= routes when they are
    # sent via POST.
    config.add_tween("warehouse.config.require_https_tween_factory")

    # Enable compression of our HTTP responses
    config.add_tween(
        "warehouse.utils.compression.compression_tween_factory",
        over=[
            "warehouse.cache.http.conditional_http_tween_factory",
            "pyramid_debugtoolbar.toolbar_tween_factory",
            "warehouse.raven.raven_tween_factory",
            EXCVIEW,
        ],
    )

    # Enable Warehouse to serve our static files
    prevent_http_cache = \
        config.get_settings().get("pyramid.prevent_http_cache", False)
    config.add_static_view(
        "static",
        "warehouse:static/dist/",
        # Don't cache at all if prevent_http_cache is true, else we'll cache
        # the files for 10 years.
        cache_max_age=0 if prevent_http_cache else 10 * 365 * 24 * 60 * 60,
    )
    config.add_cache_buster(
        "warehouse:static/dist/",
        ManifestCacheBuster(
            "warehouse:static/dist/manifest.json",
            reload=config.registry.settings["pyramid.reload_assets"],
            strict=not prevent_http_cache,
        ),
    )
    config.whitenoise_serve_static(
        autorefresh=prevent_http_cache,
        max_age=0 if prevent_http_cache else 10 * 365 * 24 * 60 * 60,
        manifest="warehouse:static/dist/manifest.json",
    )
    config.whitenoise_add_files("warehouse:static/dist/", prefix="/static/")

    # Enable Warehouse to serve our locale files
    config.add_static_view("locales", "warehouse:locales/")

    # Enable support of passing certain values like remote host, client
    # address, and protocol support in from an outer proxy to the application.
    config.add_wsgi_middleware(
        ProxyFixer,
        token=config.registry.settings["warehouse.token"],
        num_proxies=config.registry.settings.get("warehouse.num_proxies", 1),
    )

    # Protect against cache poisoning via the X-Vhm-Root headers.
    config.add_wsgi_middleware(VhmRootRemover)

    # Fix our host header when getting sent upload.pypi.io as a HOST.
    # TODO: Remove this, this is at the wrong layer.
    config.add_wsgi_middleware(HostRewrite)

    # We want Raven to be the last things we add here so that it's the outer
    # most WSGI middleware.
    config.include(".raven")

    # Register Content-Security-Policy service
    config.include(".csp")

    # Register Referrer-Policy service
    config.include(".referrer_policy")

    config.add_settings({
        "http": {
            "verify": "/etc/ssl/certs/",
        },
    })
    config.include(".http")

    # Add our theme if one was configured
    if config.get_settings().get("warehouse.theme"):
        config.include(config.get_settings()["warehouse.theme"])

    # Scan everything for configuration
    config.scan(
        ignore=[
            "warehouse.migrations.env",
            "warehouse.celery",
            "warehouse.wsgi",
        ],
    )

    # Finally, commit all of our changes
    config.commit()

    return config
