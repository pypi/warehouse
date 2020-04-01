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

import click
import pretend

import warehouse.cli
import warehouse.config


def test_lazy_config_delays(monkeypatch):
    config = pretend.stub(foo="bar", another="thing")
    configure = pretend.call_recorder(lambda a, settings: config)
    monkeypatch.setattr(warehouse.config, "configure", configure)

    lconfig = warehouse.cli.LazyConfig("thing", settings={"lol": "wat"})

    assert configure.calls == []
    assert lconfig.foo == "bar"
    assert configure.calls == [pretend.call("thing", settings={"lol": "wat"})]
    assert lconfig.another == "thing"
    assert configure.calls == [pretend.call("thing", settings={"lol": "wat"})]


def test_cli_no_settings(monkeypatch, cli):
    config = pretend.stub()
    configure = pretend.call_recorder(lambda: config)
    monkeypatch.setattr(warehouse.cli, "LazyConfig", configure)

    @warehouse.cli.warehouse.command()
    @click.pass_obj
    def cli_test_command(obj):
        assert obj is config

    result = cli.invoke(warehouse.cli.warehouse, ["cli-test-command"])

    assert result.exit_code == 0
    assert configure.calls == [pretend.call()]
