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

import os.path

import guard
import importlib
import mock
import pretend
import pytest

from werkzeug.exceptions import HTTPException
from werkzeug.test import create_environ

import warehouse

from warehouse import application, cli
from warehouse.application import Warehouse


def test_basic_instantiation():
    Warehouse({
        "debug": False,
        "database": {
            "url": "postgres:///test_warehouse",
        },
        "redis": {
            "url": "redis://localhost:6379/0"
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


def test_wsgi_app(app, monkeypatch):
    match = pretend.stub(
        match=pretend.call_recorder(lambda: ("warehouse.fake.view", {}))
    )
    urls = pretend.stub(bind_to_environ=pretend.call_recorder(lambda e: match))
    response = pretend.call_recorder(lambda e, s: None)
    fake_view = pretend.call_recorder(lambda *a, **k: response)
    fake_module = pretend.stub(view=fake_view)
    import_module = pretend.call_recorder(lambda mod: fake_module)

    monkeypatch.setattr(importlib, "import_module", import_module)

    environ = create_environ()
    start_response = pretend.stub(__name__=str("start_response"))

    app.urls = urls
    app.wsgi_app(environ, start_response)

    assert match.match.calls == [pretend.call()]
    assert urls.bind_to_environ.calls == [pretend.call(environ)]
    assert import_module.calls == [pretend.call("warehouse.fake")]
    assert fake_view.calls == [pretend.call(app, mock.ANY)]
    assert response.calls == [pretend.call(environ, mock.ANY)]


def test_wsgi_app_exception(app, monkeypatch):
    match = pretend.stub(
        match=pretend.call_recorder(lambda: ("warehouse.fake.view", {}))
    )
    urls = pretend.stub(bind_to_environ=pretend.call_recorder(lambda e: match))
    response = pretend.call_recorder(lambda e, s: None)

    class FakeException(HTTPException):

        #@pretend.call_recorder
        def __call__(self, *args, **kwargs):
            return response

    @pretend.call_recorder
    def fake_view(*args, **kwargs):
        raise FakeException("An error has occurred")

    fake_module = pretend.stub(view=fake_view)
    import_module = pretend.call_recorder(lambda mod: fake_module)

    monkeypatch.setattr(importlib, "import_module", import_module)

    environ = create_environ()
    start_response = pretend.stub(__name__=str("start_response"))

    app.urls = urls

    app.wsgi_app(environ, start_response)

    assert match.match.calls == [pretend.call()]
    assert urls.bind_to_environ.calls == [pretend.call(environ)]
    assert import_module.calls == [pretend.call("warehouse.fake")]
    assert fake_view.calls == [pretend.call(app, mock.ANY)]


def test_static_middleware(monkeypatch):
    SharedDataMiddleware = pretend.call_recorder(lambda app, c: app)

    monkeypatch.setattr(
        application,
        "SharedDataMiddleware",
        SharedDataMiddleware,
    )

    Warehouse.from_yaml(
        os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "test_config.yml",
        )),
    )

    assert SharedDataMiddleware.calls == [
        pretend.call(
            mock.ANY,
            {
                "/static/": os.path.abspath(
                    os.path.join(
                        os.path.dirname(warehouse.__file__),
                        "static",
                        "compiled",
                    ),
                ),
            },
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
