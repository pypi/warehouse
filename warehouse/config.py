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

import base64
import distutils.util
import enum
import json
import os
import shlex

from datetime import timedelta

import orjson
import transaction

from pyramid import renderers
from pyramid.authorization import Allow, Authenticated
from pyramid.config import Configurator as _Configurator
from pyramid.exceptions import HTTPForbidden
from pyramid.tweens import EXCVIEW
from pyramid_rpc.xmlrpc import XMLRPCRenderer

from warehouse.authnz import Permissions
from warehouse.utils.static import ManifestCacheBuster
from warehouse.utils.wsgi import ProxyFixer, VhmRootRemover


class Environment(str, enum.Enum):
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

    def __init__(self, request):
        pass


def require_https_tween_factory(handler, registry):
    if not registry.settings.get("enforce_https", True):
        return handler

    def require_https_tween(request):
        # If we have an :action URL and we're not using HTTPS, then we want to
        # return a 403 error.
        if request.params.get(":action", None) and request.scheme != "https":
            resp = HTTPForbidden(body="SSL is required.", content_type="text/plain")
            resp.status = "403 SSL is required"
            resp.headers["X-Fastly-Error"] = "803"
            return resp

        return handler(request)

    return require_https_tween


def activate_hook(request):
    if request.path.startswith(("/_debug_toolbar/", "/static/")):
        return False
    return True


def template_view(config, name, route, template, route_kw=None, view_kw=None):
    if route_kw is None:
        route_kw = {}
    if view_kw is None:
        view_kw = {}

    config.add_route(name, route, **route_kw)
    config.add_view(renderer=template, route_name=name, **view_kw)


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


def from_base64_encoded_json(configuration):
    return json.loads(base64.urlsafe_b64decode(configuration.encode("ascii")))


def configure(settings=None):
    if settings is None:
        settings = {}

    # Allow configuring the log level. See `warehouse/logging.py` for more
    maybe_set(settings, "logging.level", "LOG_LEVEL")

    # Add information about the current copy of the code.
    maybe_set(settings, "warehouse.commit", "SOURCE_COMMIT", default="null")

    # Set the environment from an environment variable, if one hasn't already
    # been set.
    maybe_set(
        settings,
        "warehouse.env",
        "WAREHOUSE_ENV",
        Environment,
        default=Environment.production,
    )

    # Pull in default configuration from the environment.
    maybe_set(settings, "warehouse.token", "WAREHOUSE_TOKEN")
    maybe_set(settings, "warehouse.ip_salt", "WAREHOUSE_IP_SALT")
    maybe_set(settings, "warehouse.num_proxies", "WAREHOUSE_NUM_PROXIES", int)
    maybe_set(settings, "warehouse.domain", "WAREHOUSE_DOMAIN")
    maybe_set(settings, "forklift.domain", "FORKLIFT_DOMAIN")
    maybe_set(settings, "auth.domain", "AUTH_DOMAIN")
    maybe_set(settings, "warehouse.legacy_domain", "WAREHOUSE_LEGACY_DOMAIN")
    maybe_set(settings, "site.name", "SITE_NAME", default="Warehouse")
    maybe_set(settings, "aws.key_id", "AWS_ACCESS_KEY_ID")
    maybe_set(settings, "aws.secret_key", "AWS_SECRET_ACCESS_KEY")
    maybe_set(settings, "aws.region", "AWS_REGION")
    maybe_set(settings, "b2.application_key_id", "B2_APPLICATION_KEY_ID")
    maybe_set(settings, "b2.application_key", "B2_APPLICATION_KEY")
    maybe_set(settings, "gcloud.project", "GCLOUD_PROJECT")
    maybe_set(
        settings,
        "gcloud.service_account_info",
        "GCLOUD_SERVICE_JSON",
        from_base64_encoded_json,
    )
    maybe_set(
        settings, "warehouse.release_files_table", "WAREHOUSE_RELEASE_FILES_TABLE"
    )
    maybe_set(settings, "github.token", "GITHUB_TOKEN")
    maybe_set(
        settings,
        "github.token_scanning_meta_api.url",
        "GITHUB_TOKEN_SCANNING_META_API_URL",
        default="https://api.github.com/meta/public_keys/token_scanning",
    )
    maybe_set(settings, "warehouse.downloads_table", "WAREHOUSE_DOWNLOADS_TABLE")
    maybe_set(settings, "celery.broker_url", "BROKER_URL")
    maybe_set(settings, "celery.result_url", "REDIS_URL")
    maybe_set(settings, "celery.scheduler_url", "REDIS_URL")
    maybe_set(settings, "oidc.jwk_cache_url", "REDIS_URL")
    maybe_set(settings, "database.url", "DATABASE_URL")
    maybe_set(settings, "opensearch.url", "OPENSEARCH_URL")
    maybe_set(settings, "sentry.dsn", "SENTRY_DSN")
    maybe_set(settings, "sentry.transport", "SENTRY_TRANSPORT")
    maybe_set(settings, "sessions.url", "REDIS_URL")
    maybe_set(settings, "ratelimit.url", "REDIS_URL")
    maybe_set(settings, "captcha.backend", "CAPTCHA_BACKEND")
    maybe_set(settings, "recaptcha.site_key", "RECAPTCHA_SITE_KEY")
    maybe_set(settings, "recaptcha.secret_key", "RECAPTCHA_SECRET_KEY")
    maybe_set(settings, "hcaptcha.site_key", "HCAPTCHA_SITE_KEY")
    maybe_set(settings, "hcaptcha.secret_key", "HCAPTCHA_SECRET_KEY")
    maybe_set(settings, "sessions.secret", "SESSION_SECRET")
    maybe_set(settings, "camo.url", "CAMO_URL")
    maybe_set(settings, "camo.key", "CAMO_KEY")
    maybe_set(settings, "docs.url", "DOCS_URL")
    maybe_set(settings, "ga.tracking_id", "GA_TRACKING_ID")
    maybe_set(settings, "ga4.tracking_id", "GA4_TRACKING_ID")
    maybe_set(settings, "statuspage.url", "STATUSPAGE_URL")
    maybe_set(settings, "hibp.api_key", "HIBP_API_KEY")
    maybe_set(settings, "token.password.secret", "TOKEN_PASSWORD_SECRET")
    maybe_set(settings, "token.email.secret", "TOKEN_EMAIL_SECRET")
    maybe_set(settings, "token.two_factor.secret", "TOKEN_TWO_FACTOR_SECRET")
    maybe_set(settings, "token.remember_device.secret", "TOKEN_REMEMBER_DEVICE_SECRET")
    maybe_set(
        settings,
        "warehouse.xmlrpc.search.enabled",
        "WAREHOUSE_XMLRPC_SEARCH",
        coercer=distutils.util.strtobool,
        default=True,
    )
    maybe_set(settings, "warehouse.xmlrpc.cache.url", "REDIS_URL")
    maybe_set(
        settings,
        "warehouse.xmlrpc.client.ratelimit_string",
        "XMLRPC_RATELIMIT_STRING",
        default="3600 per hour",
    )
    maybe_set(settings, "token.password.max_age", "TOKEN_PASSWORD_MAX_AGE", coercer=int)
    maybe_set(settings, "token.email.max_age", "TOKEN_EMAIL_MAX_AGE", coercer=int)
    maybe_set(
        settings,
        "token.two_factor.max_age",
        "TOKEN_TWO_FACTOR_MAX_AGE",
        coercer=int,
        default=300,
    )
    maybe_set(
        settings,
        "remember_device.days",
        "REMEMBER_DEVICE_DAYS",
        coercer=int,
        default=30,
    )
    settings.setdefault(
        "remember_device.seconds",
        timedelta(days=settings.get("remember_device.days")).total_seconds(),
    )
    settings.setdefault(
        "token.remember_device.max_age", settings.get("remember_device.seconds")
    )
    maybe_set(
        settings,
        "token.default.max_age",
        "TOKEN_DEFAULT_MAX_AGE",
        coercer=int,
        default=21600,  # 6 hours
    )
    maybe_set(
        settings,
        "reconcile_file_storages.batch_size",
        "RECONCILE_FILE_STORAGES_BATCH_SIZE",
        coercer=int,
        default=100,
    )
    maybe_set(
        settings,
        "metadata_backfill.batch_size",
        "METADATA_BACKFILL_BATCH_SIZE",
        coercer=int,
        default=500,
    )
    maybe_set_compound(settings, "billing", "backend", "BILLING_BACKEND")
    maybe_set_compound(settings, "files", "backend", "FILES_BACKEND")
    maybe_set_compound(settings, "archive_files", "backend", "ARCHIVE_FILES_BACKEND")
    maybe_set_compound(settings, "simple", "backend", "SIMPLE_BACKEND")
    maybe_set_compound(settings, "docs", "backend", "DOCS_BACKEND")
    maybe_set_compound(settings, "sponsorlogos", "backend", "SPONSORLOGOS_BACKEND")
    maybe_set_compound(settings, "origin_cache", "backend", "ORIGIN_CACHE")
    maybe_set_compound(settings, "mail", "backend", "MAIL_BACKEND")
    maybe_set_compound(settings, "metrics", "backend", "METRICS_BACKEND")
    maybe_set_compound(settings, "breached_emails", "backend", "BREACHED_EMAILS")
    maybe_set_compound(settings, "breached_passwords", "backend", "BREACHED_PASSWORDS")
    maybe_set(
        settings,
        "oidc.backend",
        "OIDC_BACKEND",
        default="warehouse.oidc.services.OIDCPublisherService",
    )

    # Pythondotorg integration settings
    maybe_set(
        settings,
        "pythondotorg.host",
        "PYTHONDOTORG_HOST",
        default="https://www.python.org",
    )
    maybe_set(settings, "pythondotorg.api_token", "PYTHONDOTORG_API_TOKEN")

    # Helpscout integration settings
    maybe_set(
        settings, "admin.helpscout.app_secret", "HELPSCOUT_APP_SECRET", default=None
    )
    maybe_set(settings, "helpscout.app_id", "HELPSCOUT_WAREHOUSE_APP_ID")
    maybe_set(settings, "helpscout.app_secret", "HELPSCOUT_WAREHOUSE_APP_SECRET")
    maybe_set(settings, "helpscout.mailbox_id", "HELPSCOUT_WAREHOUSE_MAILBOX_ID")

    # Configure our ratelimiters
    maybe_set(
        settings,
        "warehouse.account.user_login_ratelimit_string",
        "USER_LOGIN_RATELIMIT_STRING",
        default="10 per 5 minutes",
    )
    maybe_set(
        settings,
        "warehouse.account.ip_login_ratelimit_string",
        "IP_LOGIN_RATELIMIT_STRING",
        default="10 per 5 minutes",
    )
    maybe_set(
        settings,
        "warehouse.account.global_login_ratelimit_string",
        "GLOBAL_LOGIN_RATELIMIT_STRING",
        default="1000 per 5 minutes",
    )
    maybe_set(
        settings,
        "warehouse.account.email_add_ratelimit_string",
        "EMAIL_ADD_RATELIMIT_STRING",
        default="2 per day",
    )
    maybe_set(
        settings,
        "warehouse.account.verify_email_ratelimit_string",
        "VERIFY_EMAIL_RATELIMIT_STRING",
        default="3 per 6 hours",
    )
    maybe_set(
        settings,
        "warehouse.account.accounts_search_ratelimit_string",
        "ACCOUNTS_SEARCH_RATELIMIT_STRING",
        default="100 per hour",
    ),
    maybe_set(
        settings,
        "warehouse.account.password_reset_ratelimit_string",
        "PASSWORD_RESET_RATELIMIT_STRING",
        default="5 per day",
    )
    maybe_set(
        settings,
        "warehouse.manage.oidc.user_registration_ratelimit_string",
        "USER_OIDC_REGISTRATION_RATELIMIT_STRING",
        default="100 per day",
    )
    maybe_set(
        settings,
        "warehouse.manage.oidc.ip_registration_ratelimit_string",
        "IP_OIDC_REGISTRATION_RATELIMIT_STRING",
        default="100 per day",
    )
    maybe_set(
        settings,
        "warehouse.packaging.project_create_user_ratelimit_string",
        "PROJECT_CREATE_USER_RATELIMIT_STRING",
        default="20 per hour",
    )
    maybe_set(
        settings,
        "warehouse.packaging.project_create_ip_ratelimit_string",
        "PROJECT_CREATE_IP_RATELIMIT_STRING",
        default="40 per hour",
    )

    # OIDC feature flags and settings
    maybe_set(settings, "warehouse.oidc.audience", "OIDC_AUDIENCE")

    maybe_set(
        settings,
        "warehouse.organizations.max_undecided_organization_applications",
        "ORGANIZATION_MAX_UNDECIDED_APPLICATIONS",
        coercer=int,
        default=3,
    )

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
        maybe_set(
            settings,
            "livereload.url",
            "LIVERELOAD_URL",
            default="http://localhost:35729",
        )

    # Actually setup our Pyramid Configurator with the values pulled in from
    # the environment as well as the ones passed in to the configure function.
    config = Configurator(settings=settings)
    config.set_root_factory(RootFactory)

    # Register support for services
    config.include("pyramid_services")

    # Register metrics
    config.include(".metrics")

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

    # Our translation strings are all in the "messages" domain
    config.add_settings({"jinja2.i18n.domain": "messages"})

    # Trim the Jinja blocks from the output, it's extra whitespace.
    config.add_settings({"jinja2.lstrip_blocks": True})
    config.add_settings({"jinja2.trim_blocks": True})

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
        [
            "warehouse.utils.html.ClientSideIncludeExtension",
            "warehouse.i18n.extensions.TrimmedTranslatableTagsExtension",
        ],
    )

    # We'll want to configure some filters for Jinja2 as well.
    filters = config.get_settings().setdefault("jinja2.filters", {})
    filters.setdefault("format_classifiers", "warehouse.filters:format_classifiers")
    filters.setdefault("classifier_id", "warehouse.filters:classifier_id")
    filters.setdefault("format_tags", "warehouse.filters:format_tags")
    filters.setdefault("json", "warehouse.filters:tojson")
    filters.setdefault("camoify", "warehouse.filters:camoify")
    filters.setdefault("shorten_number", "warehouse.filters:shorten_number")
    filters.setdefault("urlparse", "warehouse.filters:urlparse")
    filters.setdefault("contains_valid_uris", "warehouse.filters:contains_valid_uris")
    filters.setdefault("format_package_type", "warehouse.filters:format_package_type")
    filters.setdefault("parse_version", "warehouse.filters:parse_version")
    filters.setdefault("localize_datetime", "warehouse.filters:localize_datetime")
    filters.setdefault("ctime", "warehouse.filters:ctime")
    filters.setdefault("is_recent", "warehouse.filters:is_recent")
    filters.setdefault("canonicalize_name", "packaging.utils:canonicalize_name")
    filters.setdefault("format_email", "warehouse.filters:format_email")
    filters.setdefault(
        "remove_invalid_xml_unicode", "warehouse.filters:remove_invalid_xml_unicode"
    )

    # We also want to register some global functions for Jinja
    jglobals = config.get_settings().setdefault("jinja2.globals", {})
    jglobals.setdefault("is_valid_uri", "warehouse.utils.http:is_valid_uri")
    jglobals.setdefault("gravatar", "warehouse.utils.gravatar:gravatar")
    jglobals.setdefault("gravatar_profile", "warehouse.utils.gravatar:profile")
    jglobals.setdefault("now", "warehouse.utils:now")

    # And some enums to reuse in the templates
    jglobals.setdefault("AdminFlagValue", "warehouse.admin.flags:AdminFlagValue")
    jglobals.setdefault("EventTag", "warehouse.events.tags:EventTag")
    jglobals.setdefault("Permissions", "warehouse.authnz:Permissions")
    jglobals.setdefault(
        "OrganizationInvitationStatus",
        "warehouse.organizations.models:OrganizationInvitationStatus",
    )
    jglobals.setdefault(
        "OrganizationRoleType", "warehouse.organizations.models:OrganizationRoleType"
    )
    jglobals.setdefault(
        "OrganizationType", "warehouse.organizations.models:OrganizationType"
    )
    jglobals.setdefault(
        "RoleInvitationStatus", "warehouse.packaging.models:RoleInvitationStatus"
    )
    jglobals.setdefault(
        "TeamProjectRoleType", "warehouse.organizations.models:TeamProjectRoleType"
    )

    # We'll store all of our templates in one location, warehouse/templates
    # so we'll go ahead and add that to the Jinja2 search path.
    config.add_jinja2_search_path("warehouse:templates", name=".html")
    config.add_jinja2_search_path("warehouse:templates", name=".txt")
    config.add_jinja2_search_path("warehouse:templates", name=".xml")

    # We want to configure our JSON renderer to sort the keys, and also to use
    # an ultra compact serialization format.
    config.add_renderer(
        "json",
        renderers.JSON(
            serializer=orjson.dumps,
            option=orjson.OPT_SORT_KEYS | orjson.OPT_APPEND_NEWLINE,
        ),
    )

    # Configure retry support.
    config.add_settings({"retry.attempts": 3})
    config.include("pyramid_retry")

    # Configure our transaction handling so that each request gets its own
    # transaction handler and the lifetime of the transaction is tied to the
    # lifetime of the request.
    config.add_settings(
        {
            "tm.manager_hook": lambda request: transaction.TransactionManager(),
            "tm.activate_hook": activate_hook,
            "tm.annotate_user": False,
        }
    )
    config.include("pyramid_tm")

    # Register our XMLRPC service
    config.include(".legacy.api.xmlrpc")

    # Register our XMLRPC cache
    config.include(".legacy.api.xmlrpc.cache")

    # Register support for XMLRPC and override it's renderer to allow
    # specifying custom dumps arguments.
    config.include("pyramid_rpc.xmlrpc")
    config.add_renderer("xmlrpc", XMLRPCRenderer(allow_none=True))

    # Register support for our legacy action URLs
    config.include(".legacy.action_routing")

    # Register support for our custom predicates
    config.include(".predicates")

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

    config.include(".search")

    # Register the support for AWS, Backblaze,and Google Cloud
    config.include(".aws")
    config.include(".b2")
    config.include(".gcloud")

    # Register our session support
    config.include(".sessions")

    # Register our support for http and origin caching
    config.include(".cache.http")
    config.include(".cache.origin")

    # Register support for sending emails
    config.include(".email")

    # Register our authentication support.
    config.include(".accounts")

    # Register support for Macaroon based authentication
    config.include(".macaroons")

    # Register support for OIDC based authentication
    config.include(".oidc")

    # Register logged-in views
    config.include(".manage")

    # Register our organization support.
    config.include(".organizations")

    # Register our subscription support.
    config.include(".subscriptions")

    # Allow the packaging app to register any services it has.
    config.include(".packaging")

    # Configure redirection support
    config.include(".redirects")  # internal
    config.include("pyramid_redirect")  # external
    config.add_settings({"pyramid_redirect.structlog": True})

    # Register all our URL routes for Warehouse.
    config.include(".routes")

    # Allow the sponsors app to list sponsors
    config.include(".sponsors")

    # Allow the banners app to list banners
    config.include(".banners")

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
            EXCVIEW,
        ],
    )

    # Enable Warehouse to serve our static files
    prevent_http_cache = config.get_settings().get("pyramid.prevent_http_cache", False)
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
    )
    config.whitenoise_add_files("warehouse:static/dist/", prefix="/static/")
    config.whitenoise_add_manifest(
        "warehouse:static/dist/manifest.json", prefix="/static/"
    )

    # Set up API configuration
    config.include(".api.config")

    # Enable support of passing certain values like remote host, client
    # address, and protocol support in from an outer proxy to the application.
    config.add_wsgi_middleware(
        ProxyFixer,
        token=config.registry.settings["warehouse.token"],
        ip_salt=config.registry.settings["warehouse.ip_salt"],
        num_proxies=config.registry.settings.get("warehouse.num_proxies", 1),
    )

    # Protect against cache poisoning via the X-Vhm-Root headers.
    config.add_wsgi_middleware(VhmRootRemover)

    # Add our extensions to Request
    config.include(".utils.wsgi")

    # We want Sentry to be the last things we add here so that it's the outer
    # most WSGI middleware.
    config.include(".sentry")

    # Register Content-Security-Policy service
    config.include(".csp")

    # Register Referrer-Policy service
    config.include(".referrer_policy")

    # Register Captcha service
    config.include(".captcha")

    config.add_settings({"http": {"verify": "/etc/ssl/certs/"}})
    config.include(".http")

    # Register our row counting maintenance
    config.include(".utils.row_counter")

    # Scan everything for configuration
    config.scan(
        categories=(
            "pyramid",
            "warehouse",
        ),
        ignore=["warehouse.migrations.env", "warehouse.celery", "warehouse.wsgi"],
    )

    # Sanity check our request and responses.
    # Note: It is very important that this go last. We need everything else that might
    #       have added a tween to be registered prior to this.
    config.include(".sanity")

    # Finally, commit all of our changes
    config.commit()

    return config
