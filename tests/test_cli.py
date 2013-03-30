import os
import sys
import unittest.mock

import pytest

from django.core import management
from warehouse.__main__ import main


@pytest.mark.parametrize(("args", "expected_args", "expected_environ"), [
    (["warehouse", "fake"], ["warehouse", "fake"], {}),
    (
        ["warehouse", "fake", "-c", "config.yaml"],
        ["warehouse", "fake"],
        {"WAREHOUSE_CONF": "config.yaml"},
    ),
    (
        ["warehouse", "fake", "-c", "config.yaml", "-e", "production"],
        ["warehouse", "fake"],
        {"WAREHOUSE_CONF": "config.yaml", "WAREHOUSE_ENV": "production"},
    ),
])
def test_cli_main(args, expected_args, expected_environ, monkeypatch):
    environ = {}
    executor = unittest.mock.Mock(return_value=None)

    monkeypatch.setattr(sys, "argv", args)
    monkeypatch.setattr(os, "environ", environ)
    monkeypatch.setattr(management, "execute_from_command_line", executor)

    main()

    executor.assert_called_once_with(expected_args)
    assert environ == expected_environ
