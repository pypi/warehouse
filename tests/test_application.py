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

import mock
import pretend
import pytest

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


def test_calling_application_is_wsgi_app():
    app = Warehouse.from_yaml(
        os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "test_config.yml",
        )),
    )

    app.wsgi_app = pretend.call_recorder(lambda e, s: None)

    environ, start_response = pretend.stub(), pretend.stub()
    app(environ, start_response)

    assert app.wsgi_app.calls == [pretend.call(environ, start_response)]
