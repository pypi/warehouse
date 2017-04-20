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

import alembic.command
import pretend
import pytest

from warehouse.cli.db.branches import branches
from warehouse.cli.db.current import current
from warehouse.cli.db.downgrade import downgrade
from warehouse.cli.db.heads import heads
from warehouse.cli.db.history import history
from warehouse.cli.db.merge import merge
from warehouse.cli.db.revision import revision
from warehouse.cli.db.show import show
from warehouse.cli.db.stamp import stamp
from warehouse.cli.db.upgrade import upgrade


def test_branches_command(monkeypatch, cli, pyramid_config):
    alembic_branches = pretend.call_recorder(lambda config: None)
    monkeypatch.setattr(alembic.command, "branches", alembic_branches)

    alembic_config = pretend.stub(attributes={})
    pyramid_config.alembic_config = lambda: alembic_config

    connection = pretend.stub(
        __enter__=lambda: connection,
        __exit__=lambda *a, **k: None,
        execute=pretend.call_recorder(lambda sql: None),
    )
    engine = pretend.stub(begin=lambda: connection)
    pyramid_config.registry["sqlalchemy.engine"] = engine

    result = cli.invoke(branches, obj=pyramid_config)
    assert result.exit_code == 0
    assert alembic_config.attributes == {"connection": connection}
    assert connection.execute.calls == [
        pretend.call("SELECT pg_advisory_lock(hashtext('alembic'))"),
        pretend.call("SELECT pg_advisory_unlock(hashtext('alembic'))"),
    ]
    assert alembic_branches.calls == [pretend.call(alembic_config)]


def test_current_command(monkeypatch, cli, pyramid_config):
    alembic_current = pretend.call_recorder(lambda config: None)
    monkeypatch.setattr(alembic.command, "current", alembic_current)

    alembic_config = pretend.stub(attributes={})
    pyramid_config.alembic_config = lambda: alembic_config

    connection = pretend.stub(
        __enter__=lambda: connection,
        __exit__=lambda *a, **k: None,
        execute=pretend.call_recorder(lambda sql: None),
    )
    engine = pretend.stub(begin=lambda: connection)
    pyramid_config.registry["sqlalchemy.engine"] = engine

    result = cli.invoke(current, obj=pyramid_config)
    assert result.exit_code == 0
    assert alembic_config.attributes == {"connection": connection}
    assert connection.execute.calls == [
        pretend.call("SELECT pg_advisory_lock(hashtext('alembic'))"),
        pretend.call("SELECT pg_advisory_unlock(hashtext('alembic'))"),
    ]
    assert alembic_current.calls == [pretend.call(alembic_config)]


def test_downgrade_command(monkeypatch, cli, pyramid_config):
    alembic_downgrade = pretend.call_recorder(lambda config, revision: None)
    monkeypatch.setattr(alembic.command, "downgrade", alembic_downgrade)

    alembic_config = pretend.stub(attributes={})
    pyramid_config.alembic_config = lambda: alembic_config

    connection = pretend.stub(
        __enter__=lambda: connection,
        __exit__=lambda *a, **k: None,
        execute=pretend.call_recorder(lambda sql: None),
    )
    engine = pretend.stub(begin=lambda: connection)
    pyramid_config.registry["sqlalchemy.engine"] = engine

    result = cli.invoke(downgrade, ["--", "-1"], obj=pyramid_config)
    assert result.exit_code == 0
    assert alembic_config.attributes == {"connection": connection}
    assert connection.execute.calls == [
        pretend.call("SELECT pg_advisory_lock(hashtext('alembic'))"),
        pretend.call("SELECT pg_advisory_unlock(hashtext('alembic'))"),
    ]
    assert alembic_downgrade.calls == [pretend.call(alembic_config, "-1")]


@pytest.mark.parametrize(
    ("args", "ekwargs"),
    [
        ([], {"resolve_dependencies": False}),
        (["-r"], {"resolve_dependencies": True}),
        (["--resolve-dependencies"], {"resolve_dependencies": True}),
    ],
)
def test_heads_command(monkeypatch, cli, pyramid_config, args, ekwargs):
    alembic_heads = pretend.call_recorder(
        lambda config, resolve_dependencies: None
    )
    monkeypatch.setattr(alembic.command, "heads", alembic_heads)

    alembic_config = pretend.stub(attributes={})
    pyramid_config.alembic_config = lambda: alembic_config

    connection = pretend.stub(
        __enter__=lambda: connection,
        __exit__=lambda *a, **k: None,
        execute=pretend.call_recorder(lambda sql: None),
    )
    engine = pretend.stub(begin=lambda: connection)
    pyramid_config.registry["sqlalchemy.engine"] = engine

    result = cli.invoke(heads, args, obj=pyramid_config)
    assert result.exit_code == 0
    assert alembic_config.attributes == {"connection": connection}
    assert connection.execute.calls == [
        pretend.call("SELECT pg_advisory_lock(hashtext('alembic'))"),
        pretend.call("SELECT pg_advisory_unlock(hashtext('alembic'))"),
    ]
    assert alembic_heads.calls == [pretend.call(alembic_config, **ekwargs)]


def test_history_command(monkeypatch, cli, pyramid_config):
    alembic_history = pretend.call_recorder(lambda config, range: None)
    monkeypatch.setattr(alembic.command, "history", alembic_history)

    alembic_config = pretend.stub(attributes={})
    pyramid_config.alembic_config = lambda: alembic_config

    connection = pretend.stub(
        __enter__=lambda: connection,
        __exit__=lambda *a, **k: None,
        execute=pretend.call_recorder(lambda sql: None),
    )
    engine = pretend.stub(begin=lambda: connection)
    pyramid_config.registry["sqlalchemy.engine"] = engine

    result = cli.invoke(history, ["foo:bar"], obj=pyramid_config)
    assert result.exit_code == 0
    assert alembic_config.attributes == {"connection": connection}
    assert connection.execute.calls == [
        pretend.call("SELECT pg_advisory_lock(hashtext('alembic'))"),
        pretend.call("SELECT pg_advisory_unlock(hashtext('alembic'))"),
    ]
    assert alembic_history.calls == [pretend.call(alembic_config, "foo:bar")]


@pytest.mark.parametrize(
    ("args", "eargs", "ekwargs"),
    [
        (["foo"], [("foo",)], {"message": None, "branch_label": None}),
        (
            ["foo", "bar"],
            [("foo", "bar")],
            {"message": None, "branch_label": None},
        ),
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
def test_merge_command(monkeypatch, cli, pyramid_config, args, eargs, ekwargs):
    alembic_merge = pretend.call_recorder(
        lambda config, revisions, message, branch_label: None
    )
    monkeypatch.setattr(alembic.command, "merge", alembic_merge)

    alembic_config = pretend.stub(attributes={})
    pyramid_config.alembic_config = lambda: alembic_config

    connection = pretend.stub(
        __enter__=lambda: connection,
        __exit__=lambda *a, **k: None,
        execute=pretend.call_recorder(lambda sql: None),
    )
    engine = pretend.stub(begin=lambda: connection)
    pyramid_config.registry["sqlalchemy.engine"] = engine

    result = cli.invoke(merge, args, obj=pyramid_config)
    assert result.exit_code == 0
    assert alembic_config.attributes == {"connection": connection}
    assert connection.execute.calls == [
        pretend.call("SELECT pg_advisory_lock(hashtext('alembic'))"),
        pretend.call("SELECT pg_advisory_unlock(hashtext('alembic'))"),
    ]
    assert alembic_merge.calls == [
        pretend.call(alembic_config, *eargs, **ekwargs),
    ]


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
                "-m", "the message", "-a", "--head", "foo", "--splice",
                "--branch-label", "wat",
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
def test_revision_command(monkeypatch, cli, pyramid_config, args, ekwargs):
    alembic_revision = pretend.call_recorder(
        lambda config, message, autogenerate, head, splice, branch_label: None
    )
    monkeypatch.setattr(alembic.command, "revision", alembic_revision)

    alembic_config = pretend.stub(attributes={})
    pyramid_config.alembic_config = lambda: alembic_config

    connection = pretend.stub(
        __enter__=lambda: connection,
        __exit__=lambda *a, **k: None,
        execute=pretend.call_recorder(lambda sql: None),
    )
    engine = pretend.stub(begin=lambda: connection)
    pyramid_config.registry["sqlalchemy.engine"] = engine

    result = cli.invoke(revision, args, obj=pyramid_config)
    assert result.exit_code == 0
    assert alembic_config.attributes == {"connection": connection}
    assert connection.execute.calls == [
        pretend.call("SELECT pg_advisory_lock(hashtext('alembic'))"),
        pretend.call("SELECT pg_advisory_unlock(hashtext('alembic'))"),
    ]
    assert alembic_revision.calls == [pretend.call(alembic_config, **ekwargs)]


def test_show_command(monkeypatch, cli, pyramid_config):
    alembic_show = pretend.call_recorder(lambda config, revision: None)
    monkeypatch.setattr(alembic.command, "show", alembic_show)

    alembic_config = pretend.stub(attributes={})
    pyramid_config.alembic_config = lambda: alembic_config

    connection = pretend.stub(
        __enter__=lambda: connection,
        __exit__=lambda *a, **k: None,
        execute=pretend.call_recorder(lambda sql: None),
    )
    engine = pretend.stub(begin=lambda: connection)
    pyramid_config.registry["sqlalchemy.engine"] = engine

    result = cli.invoke(show, ["foo"], obj=pyramid_config)
    assert result.exit_code == 0
    assert alembic_config.attributes == {"connection": connection}
    assert connection.execute.calls == [
        pretend.call("SELECT pg_advisory_lock(hashtext('alembic'))"),
        pretend.call("SELECT pg_advisory_unlock(hashtext('alembic'))"),
    ]
    assert alembic_show.calls == [pretend.call(alembic_config, "foo")]


def test_stamp_command(monkeypatch, cli, pyramid_config):
    alembic_stamp = pretend.call_recorder(lambda config, revision: None)
    monkeypatch.setattr(alembic.command, "stamp", alembic_stamp)

    alembic_config = pretend.stub(attributes={})
    pyramid_config.alembic_config = lambda: alembic_config

    connection = pretend.stub(
        __enter__=lambda: connection,
        __exit__=lambda *a, **k: None,
        execute=pretend.call_recorder(lambda sql: None),
    )
    engine = pretend.stub(begin=lambda: connection)
    pyramid_config.registry["sqlalchemy.engine"] = engine

    result = cli.invoke(stamp, ["foo"], obj=pyramid_config)
    assert result.exit_code == 0
    assert alembic_config.attributes == {"connection": connection}
    assert connection.execute.calls == [
        pretend.call("SELECT pg_advisory_lock(hashtext('alembic'))"),
        pretend.call("SELECT pg_advisory_unlock(hashtext('alembic'))"),
    ]
    assert alembic_stamp.calls == [pretend.call(alembic_config, "foo")]


def test_upgrade_command(monkeypatch, cli, pyramid_config):
    alembic_upgrade = pretend.call_recorder(lambda config, revision: None)
    monkeypatch.setattr(alembic.command, "upgrade", alembic_upgrade)

    alembic_config = pretend.stub(attributes={})
    pyramid_config.alembic_config = lambda: alembic_config

    connection = pretend.stub(
        __enter__=lambda: connection,
        __exit__=lambda *a, **k: None,
        execute=pretend.call_recorder(lambda sql: None),
    )
    engine = pretend.stub(begin=lambda: connection)
    pyramid_config.registry["sqlalchemy.engine"] = engine

    result = cli.invoke(upgrade, ["foo"], obj=pyramid_config)
    assert result.exit_code == 0
    assert alembic_config.attributes == {"connection": connection}
    assert connection.execute.calls == [
        pretend.call("SELECT pg_advisory_lock(hashtext('alembic'))"),
        pretend.call("SELECT pg_advisory_unlock(hashtext('alembic'))"),
    ]
    assert alembic_upgrade.calls == [pretend.call(alembic_config, "foo")]
