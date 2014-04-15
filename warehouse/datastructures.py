# Copyright 2014 Donald Stufft
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
import collections


class AttributeDict(dict):

    def __init__(self, initial_data=None):
        if initial_data:
            for key, value in initial_data.items():
                if isinstance(value, collections.Mapping):
                    self[key] = AttributeDict(value)
                else:
                    self[key] = value

    def __getattr__(self, name):
        if name not in self:
            raise AttributeError("'{}' object has no attribute '{}'".format(
                self.__class__,
                name,
            ))

        return self[name]


class CaseInsensitiveMixin(dict):

    def __getitem__(self, name):
        return super(CaseInsensitiveMixin, self).__getitem__(name.upper())

    def __setitem__(self, name, value):
        super(CaseInsensitiveMixin, self).__setitem__(name.upper(), value)

    def __delitem__(self, name):
        super(CaseInsensitiveMixin, self).__delitem__(name.upper())

    def get(self, name, *args, **kwargs):
        return super(CaseInsensitiveMixin, self).get(
            name.upper(),
            *args,
            **kwargs
        )

    def update(self, data):
        super(CaseInsensitiveMixin, self).update(
            {k.upper(): v for k, v in data.items()}
        )
