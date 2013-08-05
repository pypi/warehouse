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


class BaseAdapter(object):

    def __init__(self, *args, **kwargs):
        super(BaseAdapter, self).__init__(*args, **kwargs)
        self.model = None

    def __get__(self, instance, type=None):  # pylint: disable=W0622
        if instance is not None:
            raise AttributeError(
                "Manager isn't accessible via %s instances" % type.__name__)
        return self

    def contribute_to_class(self, model, name):
        # TODO: Use weakref because of possible memory leak / circular
        #   reference.
        self.model = model

        # Add ourselves to the Model class
        setattr(model, name, self)
