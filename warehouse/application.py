# Copyright 2013 Donald Stufft
#
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

import argparse
import collections
import importlib
import logging.config
import os.path
import urllib.parse

import babel.dates
import babel.numbers
import babel.support

import guard
import passlib.context

import jinja2

import redis

import sqlalchemy
import yaml

from raven import Client
from raven.middleware import Sentry
from werkzeug.contrib.fixers import HeaderRewriterFix
from werkzeug.exceptions import HTTPException
from werkzeug.wsgi import responder
from whitenoise import WhiteNoise

import warehouse
import warehouse.cli

from warehouse import urls
from warehouse import db
from warehouse.csrf import handle_csrf
from warehouse.datastructures import AttributeDict
from warehouse.http import Request
from warehouse.middlewares import XForwardedTokenMiddleware
from warehouse.packaging import helpers as packaging_helpers
from warehouse.packaging.search import ProjectMapping
from warehouse.search.indexes import Index
from warehouse.sessions import RedisSessionStore, Session, handle_session
from warehouse.utils import merge_dict

# Register the SQLAlchemy tables by importing them
import warehouse.accounts.tables
import warehouse.packaging.tables

# Get the various models
import warehouse.accounts.db
import warehouse.packaging.db


class Warehouse(object):

    db_classes = {
        "accounts": warehouse.accounts.db.Database,
        "packaging": warehouse.packaging.db.Database,
    }

    static_dir = os.path.abspath(
        os.path.join(os.path.dirname(warehouse.__file__), "static", "compiled")
    )
    static_path = "/static/"

    def __init__(self, config, engine=None, redis_class=redis.StrictRedis):
        self.config = AttributeDict(config)

        self.metadata = db.metadata

        # configure logging
        logging.config.dictConfig(self.config.logging)

        # Connect to the database
        if engine is None and self.config.get("database", {}).get("url"):
            engine = sqlalchemy.create_engine(self.config.database.url)
        self.engine = engine

        # Create our redis connections
        self.redises = {
            key: redis_class.from_url(url)
            for key, url in self.config.redis.items()
        }

        # Create our Store instance and associate our store modules with it
        self.db = AttributeDict()
        for name, klass in self.db_classes.items():
            self.db[name] = klass(
                self,
                self.metadata,
                self.engine,
                self.redises["downloads"],
            )

        # Create our Search Index instance and associate our mappings with it
        self.search = Index(self.db, self.config.search)
        self.search.register(ProjectMapping)

        # Set up our URL routing
        self.urls = urls.urls

        # Initialize our Translations engine
        self.translations = babel.support.NullTranslations()

        # Setup our Jinja2 Environment
        self.templates = jinja2.Environment(
            autoescape=True,
            auto_reload=self.config.debug,
            extensions=[
                "jinja2.ext.i18n",
            ],
            loader=jinja2.PackageLoader("warehouse"),
        )

        # Install Babel
        self.templates.filters.update({
            "package_type_display": packaging_helpers.package_type_display,
            "format_number": babel.numbers.format_number,
            "format_decimal": babel.numbers.format_decimal,
            "format_percent": babel.numbers.format_percent,
            "format_date": babel.dates.format_date,
            "format_datetime": babel.dates.format_datetime,
            "format_time": babel.dates.format_time,
        })

        # Install our translations
        self.templates.install_gettext_translations(
            self.translations,
            newstyle=True,
        )

        # Setup our password hasher
        self.passlib = passlib.context.CryptContext(
            schemes=[
                "bcrypt_sha256",
                "bcrypt",
                "django_bcrypt",
                "unix_disabled",
            ],
            default="bcrypt_sha256",
            deprecated=["auto"],
        )

        # Setup our session storage
        self.session_store = RedisSessionStore(
            self.redises["sessions"],
            session_class=Session,
        )

        # Add our Content Security Policy Middleware
        img_src = ["'self'"]
        if self.config.camo:
            camo_parsed = urllib.parse.urlparse(self.config.camo.url)
            img_src += [
                "{}://{}".format(camo_parsed.scheme, camo_parsed.netloc),
                "https://secure.gravatar.com",
            ]
        else:
            img_src += ["*"]

        self.wsgi_app = guard.ContentSecurityPolicy(
            self.wsgi_app,
            {
                "default-src": ["'self'"],
                "font-src": ["'self'", "data:"],
                "img-src": img_src,
                "style-src": ["'self'", "cloud.typography.com"],
            },
        )

        if "sentry" in self.config:
            self.wsgi_app = Sentry(self.wsgi_app, Client(**self.config.sentry))

        # Serve the static files that are packaged as part of Warehouse
        self.wsgi_app = WhiteNoise(
            self.wsgi_app,
            root=self.static_dir,
            prefix=self.static_path,
            max_age=31557600,
        )

        # Add our Powered By Middleware
        self.wsgi_app = HeaderRewriterFix(
            self.wsgi_app,
            add_headers=[
                (
                    "X-Powered-By",
                    "Warehouse {__version__} ({__build__})".format(
                        __version__=warehouse.__version__,
                        __build__=warehouse.__build__,
                    ),
                ),
            ],
        )

        # This is last because we want it processed first in the stack of
        # middlewares. This will ensure that we strip X-Forwarded-* headers
        # if the request doesn't come from Fastly
        self.wsgi_app = XForwardedTokenMiddleware(
            self.wsgi_app,
            self.config.site.access_token,
        )

    def __call__(self, environ, start_response):
        """
        Shortcut for :attr:`wsgi_app`.
        """
        return self.wsgi_app(environ, start_response)

    @classmethod
    def from_yaml(cls, *paths, **kwargs):
        # Pull out other keyword arguments
        override = kwargs.pop("override", None)

        default = os.path.abspath(os.path.join(
            os.path.dirname(warehouse.__file__),
            "config.yml",
        ))

        paths = [default] + list(paths)

        config = {}
        for path in paths:
            with open(path) as configfile:
                # Use no cover to work around a coverage bug
                config = merge_dict(  # pragma: no cover
                    config,
                    yaml.safe_load(configfile)
                )

        if override:
            config = merge_dict(config, override)

        return cls(config=config, **kwargs)

    @classmethod
    def from_cli(cls, argv):
        def _generate_parser(parser, commands):
            # Generate our commands
            subparsers = parser.add_subparsers()
            for name, command in commands.items():
                cmd_parser = subparsers.add_parser(name)

                if hasattr(command, "create_parser"):
                    command.create_parser(cmd_parser)

                if isinstance(command, collections.Mapping):
                    _generate_parser(cmd_parser, command)
                else:
                    cmd_parser.set_defaults(_cmd=command)

        parser = argparse.ArgumentParser(prog="warehouse")
        parser.add_argument("-c", "--config", action="append", dest="_configs")

        _generate_parser(parser, warehouse.cli.__commands__)

        args = parser.parse_args(argv)

        configs = args._configs if args._configs is not None else []
        app = cls.from_yaml(*configs)

        return args._cmd(
            app,
            *args._get_args(),
            **{k: v for k, v in args._get_kwargs() if not k.startswith("_")}
        )

    # The order of these decorators matter. We need @handle_session to come
    # before anything that depends on it, like @handle_csrf
    @handle_session
    @handle_csrf
    def dispatch_view(self, view, *args, **kwargs):
        return view(*args, **kwargs)

    @responder
    def wsgi_app(self, environ, start_response):
        """
        The actual WSGI application.  This is not implemented in
        `__call__` so that middlewares can be applied without losing a
        reference to the class.  So instead of doing this::

            app = MyMiddleware(app)

        It's a better idea to do this instead::

            app.wsgi_app = MyMiddleware(app.wsgi_app)

        Then you still have the original application object around and
        can continue to call methods on it.

        :param environ: a WSGI environment
        :param start_response: a callable accepting a status code,
                               a list of headers and an optional
                               exception context to start the response
        """
        try:
            # Figure out what endpoint to call
            urls = self.urls.bind_to_environ(environ)
            endpoint, kwargs = urls.match()

            # Load our view function
            modname, viewname = endpoint.rsplit(".", 1)
            module = importlib.import_module(modname)
            view = getattr(module, viewname)

            # Create our request object
            request = Request(environ)
            request.url_adapter = urls

            # Attach our trusted hosts to this request
            request.trusted_hosts = self.config.site.hosts

            # Access request.host to trigger a check against our trusted_hosts
            request.host

            # Dispatch to the loaded view function
            return self.dispatch_view(view, self, request, **kwargs)
        except HTTPException as exc:
            return exc
