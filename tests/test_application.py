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

import importlib
import mock
import pretend
import pytest

from werkzeug.exceptions import HTTPException
from werkzeug.test import create_environ

from warehouse import cli
from warehouse.application import Warehouse


def test_basic_instantiation():
    Warehouse({
        "debug": False,
        "database": {
            "url": "postgres:///test_warehouse",
        }
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
    start_response = pretend.stub()

    app.urls = urls
    app.wsgi_app(environ, start_response)

    assert match.match.calls == [pretend.call()]
    assert urls.bind_to_environ.calls == [pretend.call(environ)]
    assert import_module.calls == [pretend.call("warehouse.fake")]
    assert fake_view.calls == [pretend.call(app, mock.ANY)]
    assert response.calls == [pretend.call(environ, start_response)]


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
    start_response = pretend.stub()

    app.urls = urls

    app.wsgi_app(environ, start_response)

    assert match.match.calls == [pretend.call()]
    assert urls.bind_to_environ.calls == [pretend.call(environ)]
    assert import_module.calls == [pretend.call("warehouse.fake")]
    assert fake_view.calls == [pretend.call(app, mock.ANY)]
