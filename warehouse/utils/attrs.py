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

from sqlalchemy.orm.exc import DetachedInstanceError


def make_repr(*attrs, _self=None):

    def _repr(self=None):
        if self is None and _self is not None:
            self = _self

        try:
            return "{}({})".format(
                self.__class__.__name__,
                ", ".join("{}={}".format(a, repr(getattr(self, a))) for a in attrs),
            )
        except DetachedInstanceError:
            return "{}(<detached>)".format(self.__class__.__name__)

    return _repr
