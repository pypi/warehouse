# SPDX-License-Identifier: Apache-2.0

import alembic.command
import pytest

from warehouse.cli.db.branches import branches
from warehouse.cli.db.check import check
from warehouse.cli.db.current import current
from warehouse.cli.db.downgrade import downgrade
from warehouse.cli.db.heads import heads
from warehouse.cli.db.history import history
from warehouse.cli.db.merge import merge
from warehouse.cli.db.revision import revision
from warehouse.cli.db.show import show
from warehouse.cli.db.stamp import stamp
from warehouse.cli.db.upgrade import upgrade


def test_branches_command(mocker, cli, pyramid_config):
    alembic_branches = mocker.patch.object(alembic.command, "branches", autospec=True)

    alembic_config = mocker.sentinel.alembic_config
    pyramid_config.alembic_config = lambda: alembic_config

    result = cli.invoke(branches, obj=pyramid_config)
    assert result.exit_code == 0
    alembic_branches.assert_called_once_with(alembic_config)


def test_current_command(mocker, cli, pyramid_config):
    alembic_current = mocker.patch.object(alembic.command, "current", autospec=True)

    alembic_config = mocker.sentinel.alembic_config
    pyramid_config.alembic_config = lambda: alembic_config

    result = cli.invoke(current, obj=pyramid_config)
    assert result.exit_code == 0
    alembic_current.assert_called_once_with(alembic_config)


def test_downgrade_command(mocker, cli, pyramid_config):
    alembic_downgrade = mocker.patch.object(alembic.command, "downgrade", autospec=True)

    alembic_config = mocker.sentinel.alembic_config
    pyramid_config.alembic_config = lambda: alembic_config

    result = cli.invoke(downgrade, ["--", "-1"], obj=pyramid_config)
    assert result.exit_code == 0
    alembic_downgrade.assert_called_once_with(alembic_config, "-1")


@pytest.mark.parametrize(
    ("args", "ekwargs"),
    [
        ([], {"resolve_dependencies": False}),
        (["-r"], {"resolve_dependencies": True}),
        (["--resolve-dependencies"], {"resolve_dependencies": True}),
    ],
)
def test_heads_command(mocker, cli, pyramid_config, args, ekwargs):
    alembic_heads = mocker.patch.object(alembic.command, "heads", autospec=True)

    alembic_config = mocker.sentinel.alembic_config
    pyramid_config.alembic_config = lambda: alembic_config

    result = cli.invoke(heads, args, obj=pyramid_config)
    assert result.exit_code == 0
    alembic_heads.assert_called_once_with(alembic_config, **ekwargs)


def test_history_command(mocker, cli, pyramid_config):
    alembic_history = mocker.patch.object(alembic.command, "history", autospec=True)

    alembic_config = mocker.sentinel.alembic_config
    pyramid_config.alembic_config = lambda: alembic_config

    result = cli.invoke(history, ["foo:bar"], obj=pyramid_config)
    assert result.exit_code == 0
    alembic_history.assert_called_once_with(alembic_config, "foo:bar")


@pytest.mark.parametrize(
    ("args", "eargs", "ekwargs"),
    [
        (["foo"], [("foo",)], {"message": None, "branch_label": None}),
        (["foo", "bar"], [("foo", "bar")], {"message": None, "branch_label": None}),
        (
            ["-m", "my message", "foo"],
            [("foo",)],
            {"message": "my message", "branch_label": None},
        ),
        (
            ["--branch-label", "lol", "foo"],
            [("foo",)],
            {"message": None, "branch_label": "lol"},
        ),
    ],
)
def test_merge_command(mocker, cli, pyramid_config, args, eargs, ekwargs):
    alembic_merge = mocker.patch.object(alembic.command, "merge", autospec=True)

    alembic_config = mocker.sentinel.alembic_config
    pyramid_config.alembic_config = lambda: alembic_config

    result = cli.invoke(merge, args, obj=pyramid_config)
    assert result.exit_code == 0
    alembic_merge.assert_called_once_with(alembic_config, *eargs, **ekwargs)


@pytest.mark.parametrize(
    ("args", "ekwargs"),
    [
        (
            [],
            {
                "message": None,
                "autogenerate": False,
                "head": None,
                "splice": False,
                "branch_label": None,
            },
        ),
        (
            [
                "-m",
                "the message",
                "-a",
                "--head",
                "foo",
                "--splice",
                "--branch-label",
                "wat",
            ],
            {
                "message": "the message",
                "autogenerate": True,
                "head": "foo",
                "splice": True,
                "branch_label": "wat",
            },
        ),
    ],
)
def test_revision_command(mocker, cli, pyramid_config, args, ekwargs):
    alembic_revision = mocker.patch.object(alembic.command, "revision", autospec=True)

    alembic_config = mocker.sentinel.alembic_config
    pyramid_config.alembic_config = lambda: alembic_config

    result = cli.invoke(revision, args, obj=pyramid_config)
    assert result.exit_code == 0
    alembic_revision.assert_called_once_with(alembic_config, **ekwargs)


def test_show_command(mocker, cli, pyramid_config):
    alembic_show = mocker.patch.object(alembic.command, "show", autospec=True)

    alembic_config = mocker.sentinel.alembic_config
    pyramid_config.alembic_config = lambda: alembic_config

    result = cli.invoke(show, ["foo"], obj=pyramid_config)
    assert result.exit_code == 0
    alembic_show.assert_called_once_with(alembic_config, "foo")


def test_stamp_command(mocker, cli, pyramid_config):
    alembic_stamp = mocker.patch.object(alembic.command, "stamp", autospec=True)

    alembic_config = mocker.sentinel.alembic_config
    pyramid_config.alembic_config = lambda: alembic_config

    result = cli.invoke(stamp, ["foo"], obj=pyramid_config)
    assert result.exit_code == 0
    alembic_stamp.assert_called_once_with(alembic_config, "foo")


def test_upgrade_command(mocker, cli, pyramid_config):
    alembic_upgrade = mocker.patch.object(alembic.command, "upgrade", autospec=True)

    alembic_config = mocker.sentinel.alembic_config
    pyramid_config.alembic_config = lambda: alembic_config

    result = cli.invoke(upgrade, ["foo"], obj=pyramid_config)
    assert result.exit_code == 0
    alembic_upgrade.assert_called_once_with(alembic_config, "foo", sql=False)


def test_check_command(mocker, cli, pyramid_config):
    alembic_check = mocker.patch.object(alembic.command, "check", autospec=True)

    alembic_config = mocker.sentinel.alembic_config
    pyramid_config.alembic_config = lambda: alembic_config

    result = cli.invoke(check, obj=pyramid_config)
    assert result.exit_code == 0
    alembic_check.assert_called_once_with(alembic_config)
