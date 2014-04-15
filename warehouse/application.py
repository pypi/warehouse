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
import functools
import argparse
import collections
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

from flask import Flask, request, current_app

from raven import Client
from raven.middleware import Sentry
from werkzeug.contrib.fixers import HeaderRewriterFix
from whitenoise import WhiteNoise

import warehouse
import warehouse.cli

from warehouse import db, helpers
from warehouse.http import Response, Request
from warehouse.csrf import handle_csrf
from warehouse.datastructures import AttributeDict
from warehouse.middlewares import XForwardedTokenMiddleware
from warehouse.packaging import helpers as packaging_helpers
from warehouse.packaging.search import ProjectMapping
from warehouse.search.indexes import Index
from warehouse.utils import merge_dict
from warehouse.sessions import (
    RedisSessionStore, Session, RedisSessionInterface
)

# Register the SQLAlchemy tables by importing them
import warehouse.accounts.tables
import warehouse.packaging.tables

# Get the various models
import warehouse.accounts.db
import warehouse.packaging.db

# Import all the blueprints
from warehouse.views import blueprint as warehouse_bp
from warehouse.accounts.views import blueprint as accounts_bp
from warehouse.legacy.pypi import blueprint as pypi_bp
from warehouse.legacy.simple import blueprint as simple_bp
from warehouse.search.views import blueprint as search_bp
from warehouse.packaging.views import blueprint as packaging_bp


class Warehouse(Flask):

    request_class = Request
    response_class = Response

    db_classes = {
        "accounts": warehouse.accounts.db.Database,
        "packaging": warehouse.packaging.db.Database,
    }

    def __init__(self, config, engine=None, redis_class=redis.StrictRedis):
        # Setup our Jinja2 Environment
        self.jinja_options['extensions'].append('jinja2.ext.i18n')
        self.jinja_loader = jinja2.PackageLoader("warehouse")

        static_folder = os.path.abspath(
            os.path.join(
                os.path.dirname(warehouse.__file__),
                "static", "compiled"
            )
        )
        super(Warehouse, self).__init__(
            'warehouse',
            static_url_path='/static',
            static_folder=static_folder,
        )
        self.warehouse_config = AttributeDict(config)

        self.metadata = db.metadata

        # configure logging
        logging.config.dictConfig(self.warehouse_config.logging)

        # Connect to the database
        if engine is None and self.warehouse_config.get(
                "database", {}).get("url"):
            engine = sqlalchemy.create_engine(
                self.warehouse_config.database.url
            )
        self.engine = engine

        # Create our redis connections
        self.redises = {
            key: redis_class.from_url(url)
            for key, url in self.warehouse_config.redis.items()
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
        self.search = Index(self.db, self.warehouse_config.search)
        self.search.register(ProjectMapping)

        # Initialize our Translations engine
        self.translations = babel.support.NullTranslations()

        # Install Babel
        self.jinja_env.filters.update({
            "package_type_display": packaging_helpers.package_type_display,
            "format_number": babel.numbers.format_number,
            "format_decimal": babel.numbers.format_decimal,
            "format_percent": babel.numbers.format_percent,
            "format_date": babel.dates.format_date,
            "format_datetime": babel.dates.format_datetime,
            "format_time": babel.dates.format_time,
        })

        # Install our translations
        self.jinja_env.install_gettext_translations(
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

        # Setup our session storage and interface
        self.session_store = RedisSessionStore(
            self.redises["sessions"],
            session_class=Session,
        )
        self.session_interface = RedisSessionInterface(self.session_store)

        # Add our Content Security Policy Middleware
        img_src = ["'self'"]
        if self.warehouse_config.camo:
            camo_parsed = urllib.parse.urlparse(self.warehouse_config.camo.url)
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

        if "sentry" in self.warehouse_config:
            self.wsgi_app = Sentry(
                self.wsgi_app, Client(**self.warehouse_config.sentry)
            )

        # Add WhiteNoise middleware to serve the static files.
        self.wsgi_app = WhiteNoise(
            self.wsgi_app,
            root=static_folder,
            prefix='/static/',
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
            self.warehouse_config.site.access_token,
        )

        # Register all the blueprints
        self.register_blueprint(warehouse_bp)
        self.register_blueprint(accounts_bp)
        self.register_blueprint(pypi_bp)
        self.register_blueprint(simple_bp)
        self.register_blueprint(search_bp)
        self.register_blueprint(packaging_bp)

        # Register the CSRF handling behavior
        # to be triggered before the request
        @self.before_request
        def handle_csrf_token():
            view = current_app.view_functions[request.endpoint]
            handle_csrf(request, view)

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

    def update_template_context(self, context):
        super(Warehouse, self).update_template_context(context)
        context.update({
            "config": self.warehouse_config,
            "csrf_token": functools.partial(helpers.csrf_token, request),
            "gravatar_url": helpers.gravatar_url,
            "static_url": helpers.static_url,
        })

    def make_response(self, *args):
        """
        Handle the case where responses might be stubs for testing.
        """
        try:
            from pretend import stub
        except ImportError:     # pragma: no cover
            pass
        else:
            if isinstance(args[0], stub):
                # It's a stub, just return it
                return args[0]
        return super(Warehouse, self).make_response(*args)
