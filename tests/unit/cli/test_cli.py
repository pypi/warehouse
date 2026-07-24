# SPDX-License-Identifier: Apache-2.0

import types

import click

import warehouse.cli
import warehouse.config


def test_lazy_config_delays(mocker):
    config = types.SimpleNamespace(foo="bar", another="thing")
    configure = mocker.patch.object(
        warehouse.config, "configure", autospec=True, return_value=config
    )

    lconfig = warehouse.cli.LazyConfig(settings={"lol": "wat"})

    configure.assert_not_called()
    assert lconfig.foo == "bar"
    configure.assert_called_once_with(settings={"lol": "wat"})
    assert lconfig.another == "thing"
    configure.assert_called_once_with(settings={"lol": "wat"})


# TODO: This test doesn't actually test anything, as the command is not registered.
#  The test output is effectively "command not found".
def test_cli_no_settings(mocker, cli):
    config = mocker.sentinel.config
    configure = mocker.patch.object(
        warehouse.cli, "LazyConfig", autospec=True, return_value=config
    )

    @warehouse.cli.warehouse.command()
    @click.pass_obj
    def cli_test_command(obj):  # pragma: no cover
        assert obj is config

    result = cli.invoke(warehouse.cli.warehouse, ["cli-test-command"])

    assert result.exit_code == 2
    configure.assert_not_called()


def test_cli_help(mocker, cli):
    configure = mocker.patch.object(warehouse.cli, "LazyConfig", autospec=True)

    result = cli.invoke(warehouse.cli.warehouse, ["db", "-h"])

    assert result.exit_code == 0
    configure.assert_called_once_with()
