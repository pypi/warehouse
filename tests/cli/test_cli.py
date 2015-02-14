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

import os.path

import click
import pretend

import warehouse.cli


def test_cli_no_settings(monkeypatch, cli):
    config = pretend.stub()
    configure = pretend.call_recorder(lambda settings: config)
    monkeypatch.setattr(warehouse.cli, "configure", configure)

    @warehouse.cli.warehouse.command()
    @click.pass_obj
    def cli_test_command(obj):
        assert obj is config

    result = cli.invoke(warehouse.cli.warehouse, ["cli_test_command"])

    assert result.exit_code == 0
    assert configure.calls == [pretend.call(settings={})]


def test_cli_with_settings(monkeypatch, cli):
    config = pretend.stub()
    configure = pretend.call_recorder(lambda settings: config)
    monkeypatch.setattr(warehouse.cli, "configure", configure)

    @warehouse.cli.warehouse.command()
    @click.pass_obj
    def cli_test_command(obj):
        assert obj is config

    result = cli.invoke(
        warehouse.cli.warehouse,
        ["--config", ".", "cli_test_command"],
    )

    assert result.exit_code == 0
    assert configure.calls == [
        pretend.call(settings={"yml.location": (os.path.abspath("."),)}),
    ]
