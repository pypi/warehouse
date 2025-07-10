# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from uuid import UUID

import alembic.command
import pretend
import pytest
import sqlalchemy

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

import warehouse.cli.db.dbml
import warehouse.db

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
from warehouse.utils.db.types import datetime_now


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
    alembic_heads = pretend.call_recorder(lambda config, resolve_dependencies: None)
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
    assert alembic_history.calls == [pretend.call(alembic_config, "foo:bar")]


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
    assert alembic_merge.calls == [pretend.call(alembic_config, *eargs, **ekwargs)]


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
    assert alembic_stamp.calls == [pretend.call(alembic_config, "foo")]


def test_upgrade_command(monkeypatch, cli, pyramid_config):
    alembic_upgrade = pretend.call_recorder(lambda config, revision, sql: None)
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
    assert alembic_upgrade.calls == [pretend.call(alembic_config, "foo", sql=False)]


def test_check_command(monkeypatch, cli, pyramid_config):
    alembic_check = pretend.call_recorder(lambda config: None)
    monkeypatch.setattr(alembic.command, "check", alembic_check)

    alembic_config = pretend.stub(attributes={})
    pyramid_config.alembic_config = lambda: alembic_config

    result = cli.invoke(check, obj=pyramid_config)
    assert result.exit_code == 0
    assert alembic_check.calls == [pretend.call(alembic_config)]


def test_dbml_command(monkeypatch, cli):
    generate_dbml_file = pretend.call_recorder(lambda tables, path: None)
    monkeypatch.setattr(warehouse.cli.db.dbml, "generate_dbml_file", generate_dbml_file)

    ModelBase = pretend.stub(  # noqa
        metadata=pretend.stub(
            tables=pretend.stub(
                values=pretend.call_recorder(lambda: ["table0", "table1"])
            )
        )
    )
    monkeypatch.setattr(warehouse.db, "ModelBase", ModelBase)

    cli.invoke(warehouse.cli.db.dbml.dbml)
    assert generate_dbml_file.calls == [pretend.call(["table0", "table1"], None)]


EXPECTED_DBML = """Table _clan {
  name varchar [unique, not null]
  fetched varchar [default: `FetchedValue()`, Note: "fetched value"]
  for_the_children boolean [default: `True`]
  nice varchar
  id varchar [pk, not null, default: `gen_random_uuid()`]
  Note: "various clans"
}

Table _clan_member {
  name varchar [not null]
  clan_id varchar
  joined datetime [not null, default: `now()`]
  departed datetime
  id varchar [pk, not null, default: `gen_random_uuid()`]
}

Ref: _clan_member.clan_id > _clan.id
"""


def test_generate_dbml_file(tmp_path_factory):
    class Muddle(warehouse.db.Model):
        __abstract__ = True
        metadata = sqlalchemy.MetaData()

    class Clan(Muddle):
        __tablename__ = "_clan"
        __table_args__ = {"comment": "various clans"}

        name: Mapped[str] = mapped_column(unique=True)
        fetched: Mapped[str | None] = mapped_column(
            server_default=sqlalchemy.FetchedValue(),
            comment="fetched value",
        )
        for_the_children: Mapped[bool | None] = mapped_column(default=True)
        nice: Mapped[str | None] = mapped_column(sqlalchemy.String(length=69))

    class ClanMember(Muddle):
        __tablename__ = "_clan_member"

        name: Mapped[str]
        clan_id: Mapped[UUID | None] = mapped_column(
            PG_UUID,
            sqlalchemy.ForeignKey("_clan.id", deferrable=True, initially="DEFERRED"),
        )
        joined: Mapped[datetime_now]
        departed: Mapped[datetime | None]

    outpath = tmp_path_factory.mktemp("out") / "wutang.dbml"
    warehouse.cli.db.dbml.generate_dbml_file(Muddle.metadata.tables.values(), outpath)

    with open(outpath) as f:
        assert f.read() == EXPECTED_DBML


def test_generate_dbml_console(capsys, monkeypatch):
    class Muddle(warehouse.db.Model):
        __abstract__ = True
        metadata = sqlalchemy.MetaData()

    class Clan(Muddle):
        __tablename__ = "_clan"
        __table_args__ = {"comment": "various clans"}

        name: Mapped[str] = mapped_column(unique=True)
        fetched: Mapped[str | None] = mapped_column(
            server_default=sqlalchemy.FetchedValue(),
            comment="fetched value",
        )
        for_the_children: Mapped[bool | None] = mapped_column(default=True)
        nice: Mapped[str | None] = mapped_column(sqlalchemy.String(length=69))

    class ClanMember(Muddle):
        __tablename__ = "_clan_member"

        name: Mapped[str]
        clan_id: Mapped[UUID | None] = mapped_column(
            PG_UUID,
            sqlalchemy.ForeignKey("_clan.id", deferrable=True, initially="DEFERRED"),
        )
        joined: Mapped[datetime_now]
        departed: Mapped[datetime | None]

    warehouse.cli.db.dbml.generate_dbml_file(Muddle.metadata.tables.values(), None)
    captured = capsys.readouterr()

    assert captured.out == EXPECTED_DBML


def test_generate_dbml_bad_conversion():
    class Muddle(warehouse.db.Model):
        __abstract__ = True
        metadata = sqlalchemy.MetaData()

    class BadText(sqlalchemy.Text):
        pass

    class Puddle(Muddle):
        __tablename__ = "puddle"
        __table_args__ = {"comment": "various clans"}

        name: Mapped[str] = mapped_column(BadText, unique=True)

    with pytest.raises(SystemExit):
        warehouse.cli.db.dbml.generate_dbml_file(Muddle.metadata.tables.values(), None)
