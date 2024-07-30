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

import datetime


def now() -> datetime.datetime:
    """Return the current datetime in UTC without a timezone."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def dotted_navigator(path):
    def method(self):
        obj = self
        for item in path.split("."):
            obj = getattr(obj, item)
        return obj

    return property(method)
