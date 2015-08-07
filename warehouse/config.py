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

import fs.opener
import transaction

from pyramid import renderers
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPMovedPermanently

from warehouse.utils.static import WarehouseCacheBuster


class Environment(enum.Enum):
    production = "production"
    development = "development"


def content_security_policy_tween_factory(handler, registry):
    policy = registry.settings.get("csp", {})
    policy = "; ".join([" ".join([k] + v) for k, v in sorted(policy.items())])

    def content_security_policy_tween(request):
        resp = handler(request)

        # We don't want to apply our Content Security Policy to the debug
        # toolbar, that's not part of our application and it doesn't work with
        # our restrictive CSP.
        if not request.path.startswith("/_debug_toolbar/"):
            resp.headers["Content-Security-Policy"] = \
                policy.format(request=request)

        return resp

    return content_security_policy_tween


def activate_hook(request):
    if request.path.startswith(("/_debug_toolbar/", "/static/")):
        return False
    return True


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

    # Set the environment from an environment variable, if one hasn't already
    # been set.
    maybe_set(
        settings, "warehouse.env", "WAREHOUSE_ENV", Environment,
        default=Environment.production,
    )

    # Pull in default configuration from the environment.
    maybe_set(settings, "site.name", "SITE_NAME", default="Warehouse")
    maybe_set(settings, "aws.key_id", "AWS_ACCESS_KEY_ID")
    maybe_set(settings, "aws.secret_key", "AWS_SECRET_ACCESS_KEY")
    maybe_set(settings, "aws.region", "AWS_REGION")
    maybe_set(settings, "database.url", "DATABASE_URL")
    maybe_set(settings, "sessions.url", "REDIS_URL")
    maybe_set(settings, "download_stats.url", "REDIS_URL")
    maybe_set(settings, "sessions.secret", "SESSION_SECRET")
    maybe_set(settings, "camo.url", "CAMO_URL")
    maybe_set(settings, "camo.key", "CAMO_KEY")
    maybe_set(settings, "docs.url", "DOCS_URL")
    maybe_set(settings, "dirs.documentation", "DOCS_DIR")
    maybe_set_compound(settings, "files", "backend", "FILES_BACKEND")

    # Add the settings we use when the environment is set to development.
    if settings["warehouse.env"] == Environment.development:
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

    # Include anything needed by the development environment.
    if config.registry.settings["warehouse.env"] == Environment.development:
        config.include("pyramid_debugtoolbar")

    # Register our logging support
    config.include(".logging")

    # We'll want to use Jinja2 as our template system.
    config.include("pyramid_jinja2")

    # We want to use newstyle gettext
    config.add_settings({"jinja2.newstyle": True})

    # We also want to use Jinja2 for .html templates as well, because we just
    # assume that all templates will be using Jinja.
    config.add_jinja2_renderer(".html")

    # We'll want to configure some filters for Jinja2 as well.
    filters = config.get_settings().setdefault("jinja2.filters", {})
    filters.setdefault("readme", "warehouse.filters:readme_renderer")
    filters.setdefault("shorten_number", "warehouse.filters:shorten_number")

    # We also want to register some global functions for Jinja
    jglobals = config.get_settings().setdefault("jinja2.globals", {})
    jglobals.setdefault("gravatar", "warehouse.utils.gravatar:gravatar")

    # We'll store all of our templates in one location, warehouse/templates
    # so we'll go ahead and add that to the Jinja2 search path.
    config.add_jinja2_search_path("warehouse:templates", name=".html")

    # We want to configure our JSON renderer to sort the keys, and also to use
    # an ultra compact serialization format.
    config.add_renderer(
        "json",
        renderers.JSON(sort_keys=True, separators=(",", ":")),
    )

    # Configure our transaction handling so that each request gets it's own
    # transaction handler and the lifetime of the transaction is tied to the
    # lifetime of the request.
    config.add_settings({
        "tm.attempts": 3,
        "tm.manager_hook": lambda request: transaction.TransactionManager(),
        "tm.activate_hook": activate_hook,
        "tm.annotate_user": False,
    })
    config.include("pyramid_tm")

    # Register support for services
    config.include("pyramid_services")

    # Register support for our legacy action URLs
    config.include(".legacy.action_routing")

    # Register support for internationalization and localization
    config.include(".i18n")

    # Register the configuration for the PostgreSQL database.
    config.include(".db")

    # Register the support for AWS
    config.include(".aws")

    # Register our session support
    config.include(".sessions")

    # Register our support for http and origin caching
    config.include(".cache.http")
    config.include(".cache.origin")

    # Register our CSRF support
    config.include(".csrf")

    # Register our authentication support.
    config.include(".accounts")

    # Allow the packaging app to register any services it has.
    config.include(".packaging")

    # Configure redirection support
    config.include(".redirects")

    # Register all our URL routes for Warehouse.
    config.include(".routes")

    # Enable a Content Security Policy
    config.add_settings({
        "csp": {
            "default-src": ["'none'"],
            "frame-ancestors": ["'none'"],
            "img-src": [
                "'self'",
                config.registry.settings["camo.url"],
                "https://secure.gravatar.com",
            ],
            "referrer": ["cross-origin"],
            "reflected-xss": ["block"],
            "script-src": ["'self'"],
            "style-src": ["'self'"],
        },
    })
    config.add_tween("warehouse.config.content_security_policy_tween_factory")

    # If a route matches with a slash appended to it, redirect to that route
    # instead of returning a HTTPNotFound.
    config.add_notfound_view(append_slash=HTTPMovedPermanently)

    # Configure the filesystems we use.
    config.registry["filesystems"] = {}
    for key, path in {
            k[5:]: v
            for k, v in config.registry.settings.items()
            if k.startswith("dirs.")}.items():
        config.registry["filesystems"][key] = \
            fs.opener.fsopendir(path, create_dir=True)

    # Enable Warehouse to service our static files
    config.add_static_view(
        name="static",
        path="warehouse:static",
        cachebust=WarehouseCacheBuster(
            "warehouse:static/manifest.json",
            cache=not config.registry.settings["pyramid.reload_assets"],
        ),
    )

    # Scan everything for configuration
    config.scan(ignore=["warehouse.migrations.env"])

    return config
