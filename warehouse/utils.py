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

import collections

import six


class AttributeDict(dict):

    def __getattr__(self, name):
        if not name in self:
            raise AttributeError("'{}' object has no attribute '{}'".format(
                self.__class__,
                name,
            ))

        return self[name]


def merge_dict(base, additional, dict_class=AttributeDict):
    if base is None:
        return dict_class(additional)

    if additional is None:
        return dict_class(base)

    if not (isinstance(base, collections.Mapping)
            and isinstance(additional, collections.Mapping)):
        return dict_class(additional)

    merged = dict_class(base)
    for key, value in six.iteritems(additional):
        if isinstance(value, collections.Mapping):
            merged[key] = merge_dict(merged.get(key), value, dict_class)
        else:
            merged[key] = value

    return merged
