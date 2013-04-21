import os

import pytest

from django.core.management.base import CommandError
from warehouse.management.commands.init import Command


def test_init_command_no_path():
    with pytest.raises(CommandError):
        Command().handle()


def test_init_command_too_many_paths(tmpdir):
    with pytest.raises(CommandError):
        Command().handle(tmpdir, tmpdir)


def test_init_command_creates_config(tmpdir):
    filename = os.path.join(str(tmpdir), "config.py")
    Command().handle(filename)

    assert os.path.exists(filename)
    assert os.path.isfile(filename)
