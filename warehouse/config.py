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

import fs.opener
import transaction

from pyramid import renderers
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPMovedPermanently
from tzf.pyramid_yml import config_defaults

from warehouse.utils.static import WarehouseCacheBuster


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


def configure(settings=None):
    if settings is None:
        settings = {}

    config = Configurator(settings=settings)

    # Set our yml.location so that it contains all of our settings files
    config_defaults(config, ["warehouse:etc"])

    # We want to load configuration from YAML files
    config.include("tzf.pyramid_yml")

    # Register our logging support
    config.include(".logging")

    # We'll want to use Jinja2 as our template system.
    config.include("pyramid_jinja2")

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
        "tm.manager_hook": lambda request: transaction.TransactionManager(),
        "tm.activate_hook": activate_hook,
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
                "https://raw.githubusercontent.com",
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
