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
from __future__ import absolute_import, division, print_function
from __future__ import unicode_literals

import argparse
import collections
import importlib
import os.path

import jinja2
import six
import sqlalchemy
import yaml

from webassets import Environment as AssetsEnvironment
from webassets.ext.jinja2 import AssetsExtension
from werkzeug.exceptions import HTTPException
from werkzeug.routing import Map
from werkzeug.wsgi import SharedDataMiddleware, responder

import warehouse
import warehouse.cli

from warehouse.http import Request
from warehouse.middleware import PoweredBy
from warehouse.utils import AttributeDict, merge_dict, convert_to_attr_dict


class Warehouse(object):

    metadata = sqlalchemy.MetaData()

    model_names = {
        "packaging": "warehouse.packaging.models:Model",
    }

    url_names = [
        "warehouse.legacy.urls",
    ]

    template_packages = [
        "warehouse.ui",
        "warehouse.legacy",
        "warehouse",
    ]

    def __init__(self, config, engine=None):
        self.config = convert_to_attr_dict(config)

        # Connect to the database
        if engine is None:
            engine = sqlalchemy.create_engine(self.config.database.url)

        self.engine = engine

        # Create our Store instance and associate our store modules with it
        self.models = AttributeDict()
        for name, mod_path in six.iteritems(self.model_names):
            mod_name, klass = mod_path.rsplit(":", 1)
            mod = importlib.import_module(mod_name)
            self.models[name] = getattr(mod, klass)(self.metadata, self.engine)

        # Setup our URL routing
        url_rules = []
        for name in self.url_names:
            mod = importlib.import_module(name)
            url_rules.extend(getattr(mod, "__urls__"))
        self.urls = Map(url_rules)

        # Setup our Jinja2 Environment
        self.templates = jinja2.Environment(
            auto_reload=self.config.debug,
            extensions=[
                AssetsExtension,
            ],
            loader=jinja2.ChoiceLoader(
                [jinja2.PackageLoader(tp) for tp in self.template_packages]
            ),
        )

        # Setup our web assets environment
        asset_config = self.config.assets
        asset_config.setdefault("debug", self.config.debug)
        asset_config.setdefault("auto_build", self.config.debug)
        asset_config.setdefault("less_run_in_debug", False)

        self.templates.assets_environment = AssetsEnvironment(**asset_config)

        # Load our static directories
        static_path = os.path.abspath(
            os.path.join(os.path.dirname(warehouse.__file__), "static"),
        )
        self.templates.assets_environment.append_path(
            static_path,
            self.config.assets.url,
        )

        # Add our Powered By Middleware
        self.wsgi_app = PoweredBy(self.wsgi_app, "Warehouse {} ({})".format(
            warehouse.__version__,
            warehouse.__build__,
        ))

        # Serve the static files if we're in debug
        if self.config.debug:
            self.wsgi_app = SharedDataMiddleware(
                self.wsgi_app,
                {"/static/": static_path},
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
            for name, command in six.iteritems(commands):
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

            # Dispatch to our view
            return view(self, request, **kwargs)
        except HTTPException as exc:
            return exc
