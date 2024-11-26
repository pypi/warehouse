# SPDX-License-Identifier: Apache-2.0

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

    assert result.exit_code == 2
    assert configure.calls == []


def test_cli_help(monkeypatch, cli):
    config = pretend.stub()
    configure = pretend.call_recorder(lambda: config)
    monkeypatch.setattr(warehouse.cli, "LazyConfig", configure)

    result = cli.invoke(warehouse.cli.warehouse, ["db", "-h"])

    assert result.exit_code == 0
    assert configure.calls == [pretend.call()]
