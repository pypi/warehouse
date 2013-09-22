# Copyright 2013 Donald Stufft
#
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
from __future__ import absolute_import, division, print_function
from __future__ import unicode_literals

import argparse
import collections
import os.path

import six
import yaml

import warehouse
import warehouse.cli

from warehouse.utils import merge_dict


class Warehouse(object):

    def __init__(self, config):
        self.config = config

    @classmethod
    def from_yaml(cls, *paths):
        default = os.path.abspath(os.path.join(
            os.path.dirname(warehouse.__file__),
            "config.yml",
        ))

        paths = [default] + list(paths)

        config = {}
        for path in paths:
            with open(path) as configfile:
                config = merge_dict(config, yaml.safe_load(configfile))

        return cls(config=config)

    @classmethod
    def from_cli(cls, argv):
        def _generate_parser(parser, commands):
            # Generate our commands
            subparsers = parser.add_subparsers()
            for name, command in six.iteritems(commands):
                cmd_parser = subparsers.add_parser(name)

                if hasattr(command, "create_parser"):
                    command.create_parser(cmd_parser)

                if isinstance(command, collections.Mapping):
                    _generate_parser(cmd_parser, command)
                else:
                    cmd_parser.set_defaults(_cmd=command)

        parser = argparse.ArgumentParser(prog="warehouse")
        parser.add_argument("-c", "--config", action="append", dest="_configs")

        _generate_parser(parser, warehouse.cli.__commands__)

        args = parser.parse_args(argv)

        configs = args._configs if args._configs is not None else []
        app = cls.from_yaml(*configs)

        return args._cmd(
            app,
            *args._get_args(),
            **{k: v for k, v in args._get_kwargs() if not k.startswith("_")}
        )
