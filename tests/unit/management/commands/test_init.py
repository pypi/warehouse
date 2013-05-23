# Copyright 2013 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
