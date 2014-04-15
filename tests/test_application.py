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

from unittest import mock
import os.path

import guard
import pretend
import pytest
from jinja2 import Template
from flask import render_template

import warehouse
from warehouse import application, cli
from warehouse.application import Warehouse


def test_basic_instantiation():
    Warehouse({
        "debug": False,
        "site": {
            "access_token": "testing",
        },
        "database": {
            "url": "postgres:///test_warehouse",
        },
        "redis": {
            "downloads": "redis://localhost:6379/0",
            "sessions": "redis://localhost:6379/0",
        },
        "search": {
            "index": "warehouse",
            "hosts": [],
        },
        "camo": None,
        "logging": {
            "version": 1,
        },
    })


def test_yaml_instantiation():
    Warehouse.from_yaml(
        os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "test_config.yml",
        )),
    )


def test_cli_instantiation(capsys):
    with pytest.raises(SystemExit):
        Warehouse.from_cli(["-h"])

    out, err = capsys.readouterr()

    assert "usage: warehouse" in out
    assert not err


def test_running_cli_command(monkeypatch):
    commands = {"serve": pretend.call_recorder(lambda *a, **k: None)}
    monkeypatch.setattr(cli, "__commands__", commands)

    config = os.path.abspath(os.path.join(
        os.path.dirname(__file__),
        "test_config.yml",
    ))

    Warehouse.from_cli(["-c", config, "serve"])

    assert commands["serve"].calls == [pretend.call(mock.ANY)]


def test_calling_application_is_wsgi_app(app):
    app.wsgi_app = pretend.call_recorder(lambda e, s: None)

    environ, start_response = pretend.stub(), pretend.stub()
    app(environ, start_response)

    assert app.wsgi_app.calls == [pretend.call(environ, start_response)]


def test_static_middleware(monkeypatch):
    WhiteNoise = pretend.call_recorder(lambda app, root, prefix, max_age: app)

    monkeypatch.setattr(
        application,
        "WhiteNoise",
        WhiteNoise,
    )

    Warehouse.from_yaml(
        os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "test_config.yml",
        )),
    )

    assert WhiteNoise.calls == [
        pretend.call(
            mock.ANY,
            root=os.path.abspath(
                os.path.join(
                    os.path.dirname(warehouse.__file__),
                    "static",
                    "compiled",
                ),
            ),
            prefix="/static/",
            max_age=31557600,
        )
    ]


def test_sentry_middleware(monkeypatch):
    Sentry = pretend.call_recorder(lambda app, client: app)
    client_obj = pretend.stub()
    Client = pretend.call_recorder(lambda **kw: client_obj)

    monkeypatch.setattr(application, "Sentry", Sentry)
    monkeypatch.setattr(application, "Client", Client)

    Warehouse.from_yaml(
        os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "test_config.yml",
        )),
        override={"sentry": {"dsn": "http://public:secret@example.com/1"}}
    )

    assert Sentry.calls == [pretend.call(mock.ANY, client_obj)]
    assert Client.calls == [
        pretend.call(dsn="http://public:secret@example.com/1"),
    ]


def test_guard_middleware(monkeypatch):
    ContentSecurityPolicy = pretend.call_recorder(lambda app, policy: app)

    monkeypatch.setattr(guard, "ContentSecurityPolicy", ContentSecurityPolicy)

    Warehouse.from_yaml(
        os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "test_config.yml",
        )),
    )

    assert ContentSecurityPolicy.calls == [pretend.call(mock.ANY, mock.ANY)]


def test_camo_settings(monkeypatch):
    ContentSecurityPolicy = pretend.call_recorder(lambda app, policy: app)

    monkeypatch.setattr(guard, "ContentSecurityPolicy", ContentSecurityPolicy)

    Warehouse.from_yaml(
        os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "test_config.yml",
        )),
        override={"camo": {"url": "https://camo.example.com/", "key": "skey"}},
    )

    assert ContentSecurityPolicy.calls == [pretend.call(mock.ANY, mock.ANY)]
    assert set(ContentSecurityPolicy.calls[0].args[1]["img-src"]) == {
        "'self'",
        "https://camo.example.com",
        "https://secure.gravatar.com",
    }


def test_header_rewrite_middleware(monkeypatch):
    HeaderRewriterFix = pretend.call_recorder(lambda app, **kw: app)

    monkeypatch.setattr(application, "HeaderRewriterFix", HeaderRewriterFix)

    Warehouse.from_yaml(
        os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "test_config.yml",
        )),
    )

    assert HeaderRewriterFix.calls == [
        pretend.call(
            mock.ANY,
            add_headers=[
                (
                    "X-Powered-By",
                    "Warehouse {__version__} ({__build__})".format(
                        __version__=warehouse.__version__,
                        __build__=warehouse.__build__,
                    ),
                ),
            ],
        ),
    ]


def test_passlib_context():
    app = Warehouse.from_yaml(
        os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "test_config.yml",
        )),
    )

    assert app.passlib.to_dict() == {
        "schemes": [
            "bcrypt_sha256",
            "bcrypt",
            "django_bcrypt",
            "unix_disabled",
        ],
        "default": "bcrypt_sha256",
        "deprecated": ["auto"],
    }


def test_template_rendering(warehouse_app):
    """
    Test a simple template rendering view
    """
    @warehouse_app.route('/simple-template')
    def render_simple():
        template = Template("Hello World")
        return render_template(template)

    with warehouse_app.test_client() as c:
        c.get('/simple-template')
