# SPDX-License-Identifier: Apache-2.0

import sys

import pretend
import pytest

from warehouse import db
from warehouse.cli import shell


class TestAutoDetection:
    def test_bpython(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "bpython", pretend.stub())
        assert shell.autodetect() == "bpython"

    def test_bpython_over_ipython(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "bpython", pretend.stub())
        monkeypatch.setitem(sys.modules, "IPython", pretend.stub())
        assert shell.autodetect() == "bpython"

    def test_ipython(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "IPython", pretend.stub())
        assert shell.autodetect() == "ipython"

    def test_plain(self, monkeypatch):
        """Neither bpython nor ipython are installed."""
        monkeypatch.setitem(sys.modules, "bpython", None)
        monkeypatch.setitem(sys.modules, "IPython", None)
        assert shell.autodetect() == "plain"


class TestShells:
    def test_bpython(self, monkeypatch):
        bpython_mod = pretend.stub(embed=pretend.call_recorder(lambda a: None))
        monkeypatch.setitem(sys.modules, "bpython", bpython_mod)
        shell.bpython(one="two")

        assert bpython_mod.embed.calls == [pretend.call({"one": "two"})]

    def test_ipython(self, monkeypatch):
        ipython_mod = pretend.stub(
            start_ipython=pretend.call_recorder(lambda argv, user_ns: None)
        )
        monkeypatch.setitem(sys.modules, "IPython", ipython_mod)
        shell.ipython(two="one")

        assert ipython_mod.start_ipython.calls == [
            pretend.call(argv=[], user_ns={"two": "one"})
        ]

    def test_plain(self, monkeypatch):
        code_mod = pretend.stub(interact=pretend.call_recorder(lambda local: None))
        monkeypatch.setitem(sys.modules, "code", code_mod)
        shell.plain(three="four")

        assert code_mod.interact.calls == [pretend.call(local={"three": "four"})]


class TestCLIShell:
    def test_autodetects(self, monkeypatch, cli):
        autodetect = pretend.call_recorder(lambda: "plain")
        monkeypatch.setattr(shell, "autodetect", autodetect)

        session = pretend.stub()
        session_cls = pretend.call_recorder(lambda bind: session)
        monkeypatch.setattr(db, "Session", session_cls)

        plain = pretend.call_recorder(lambda **kw: None)
        monkeypatch.setattr(shell, "plain", plain)

        engine = pretend.stub()
        config = pretend.stub(registry={"sqlalchemy.engine": engine})

        result = cli.invoke(shell.shell, obj=config)

        assert result.exit_code == 0
        assert autodetect.calls == [pretend.call()]
        assert session_cls.calls == [pretend.call(bind=engine)]
        assert plain.calls == [pretend.call(config=config, db=session)]

    @pytest.mark.parametrize("type_", ["bpython", "ipython", "plain"])
    def test_specify_type(self, monkeypatch, cli, type_):
        autodetect = pretend.call_recorder(lambda: "plain")
        monkeypatch.setattr(shell, "autodetect", autodetect)

        session = pretend.stub()
        session_cls = pretend.call_recorder(lambda bind: session)
        monkeypatch.setattr(db, "Session", session_cls)

        runner = pretend.call_recorder(lambda **kw: None)
        monkeypatch.setattr(shell, type_, runner)

        engine = pretend.stub()
        config = pretend.stub(registry={"sqlalchemy.engine": engine})

        result = cli.invoke(shell.shell, ["--type", type_], obj=config)

        assert result.exit_code == 0
        assert autodetect.calls == []
        assert session_cls.calls == [pretend.call(bind=engine)]
        assert runner.calls == [pretend.call(config=config, db=session)]

    @pytest.mark.parametrize("type_", ["bpython", "ipython", "plain"])
    def test_unavailable_shell(self, monkeypatch, cli, type_):
        autodetect = pretend.call_recorder(lambda: "plain")
        monkeypatch.setattr(shell, "autodetect", autodetect)

        session = pretend.stub()
        session_cls = pretend.call_recorder(lambda bind: session)
        monkeypatch.setattr(db, "Session", session_cls)

        @pretend.call_recorder
        def runner(**kw):
            raise ImportError

        monkeypatch.setattr(shell, type_, runner)

        engine = pretend.stub()
        config = pretend.stub(registry={"sqlalchemy.engine": engine})

        result = cli.invoke(shell.shell, ["--type", type_], obj=config)

        assert result.exit_code == 1
        assert autodetect.calls == []
        assert session_cls.calls == [pretend.call(bind=engine)]
        assert runner.calls == [pretend.call(config=config, db=session)]
