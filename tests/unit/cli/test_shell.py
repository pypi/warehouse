# SPDX-License-Identifier: Apache-2.0

import sys

import pytest
import transaction

from warehouse import db
from warehouse.cli import shell


class TestAutoDetection:
    def test_bpython(self, monkeypatch, mocker):
        monkeypatch.setitem(sys.modules, "bpython", mocker.stub())
        assert shell.autodetect() == "bpython"

    def test_bpython_over_ipython(self, monkeypatch, mocker):
        monkeypatch.setitem(sys.modules, "bpython", mocker.stub())
        monkeypatch.setitem(sys.modules, "IPython", mocker.stub())
        assert shell.autodetect() == "bpython"

    def test_ipython(self, monkeypatch, mocker):
        monkeypatch.setitem(sys.modules, "IPython", mocker.stub())
        assert shell.autodetect() == "ipython"

    def test_plain(self, monkeypatch):
        """Neither bpython nor ipython are installed."""
        monkeypatch.setitem(sys.modules, "bpython", None)
        monkeypatch.setitem(sys.modules, "IPython", None)
        assert shell.autodetect() == "plain"


class TestShells:
    def test_bpython(self, monkeypatch, mocker):
        bpython_mod = mocker.MagicMock()
        monkeypatch.setitem(sys.modules, "bpython", bpython_mod)
        shell.bpython(one="two")

        bpython_mod.embed.assert_called_once_with({"one": "two"})

    def test_ipython(self, monkeypatch, mocker):
        ipython_mod = mocker.MagicMock()
        monkeypatch.setitem(sys.modules, "IPython", ipython_mod)
        shell.ipython(two="one")

        ipython_mod.start_ipython.assert_called_once_with(
            argv=[], user_ns={"two": "one"}
        )

    def test_plain(self, monkeypatch, mocker):
        code_mod = mocker.MagicMock()
        monkeypatch.setitem(sys.modules, "code", code_mod)
        shell.plain(three="four")

        code_mod.interact.assert_called_once_with(local={"three": "four"})


class TestCLIShell:
    def test_autodetects(self, mocker, cli, pyramid_config):
        mock_autodetect = mocker.patch.object(shell, "autodetect", return_value="plain")

        session = mocker.stub(name="session")
        mock_session_cls = mocker.patch.object(db, "Session", return_value=session)

        mock_plain = mocker.patch.object(shell, "plain")

        engine = mocker.stub(name="engine")
        pyramid_config.registry["sqlalchemy.engine"] = engine

        result = cli.invoke(shell.shell, obj=pyramid_config)

        assert result.exit_code == 0
        mock_autodetect.assert_called_once()
        mock_session_cls.assert_called_once_with(bind=engine)
        mock_plain.assert_called_once()
        call_kwargs = mock_plain.call_args.kwargs
        assert call_kwargs["config"] is pyramid_config
        assert call_kwargs["db"] is session
        assert isinstance(call_kwargs["request"].tm, transaction.TransactionManager)
        assert call_kwargs["request"].db is session

    @pytest.mark.parametrize("type_", ["bpython", "ipython", "plain"])
    def test_specify_type(self, mocker, cli, pyramid_config, type_):
        mock_autodetect = mocker.patch.object(shell, "autodetect")

        session = mocker.stub(name="session")
        engine = mocker.stub(name="engine")
        mock_session_cls = mocker.patch.object(db, "Session", return_value=session)

        mock_runner = mocker.patch.object(shell, type_)

        pyramid_config.registry["sqlalchemy.engine"] = engine

        result = cli.invoke(shell.shell, ["--type", type_], obj=pyramid_config)

        assert result.exit_code == 0
        mock_autodetect.assert_not_called()
        mock_session_cls.assert_called_once_with(bind=engine)
        mock_runner.assert_called_once()
        call_kwargs = mock_runner.call_args.kwargs
        assert call_kwargs["config"] is pyramid_config
        assert call_kwargs["db"] is session
        assert call_kwargs["request"].db is session

    @pytest.mark.parametrize("type_", ["bpython", "ipython", "plain"])
    def test_unavailable_shell(self, mocker, cli, pyramid_config, type_):
        mock_autodetect = mocker.patch.object(shell, "autodetect")

        session = mocker.stub(name="session")
        engine = mocker.stub(name="engine")
        mocker.patch.object(db, "Session", return_value=session)

        mock_runner = mocker.patch.object(shell, type_, side_effect=ImportError)

        pyramid_config.registry["sqlalchemy.engine"] = engine

        result = cli.invoke(shell.shell, ["--type", type_], obj=pyramid_config)

        assert result.exit_code == 1
        mock_autodetect.assert_not_called()
        mock_runner.assert_called_once()
