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

import os.path

import yaml

import warehouse

from warehouse.utils import merge_dict


class Warehouse(object):

    def __init__(self, config):
        self.config = config

    @classmethod
    def from_yaml(cls, *paths):
        default = os.path.join(
            os.path.dirname(warehouse.__file__),
            "config.yml",
        )

        paths = [default] + list(paths)

        config = {}
        for path in paths:
            with open(path) as configfile:
                merge_dict(config, yaml.safe_load(configfile))

        return cls(config=config)
