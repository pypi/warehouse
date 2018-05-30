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

from warehouse.utils.attrs import make_repr


class TestMakeRepr:
    def test_on_class(self):
        class Fake:
            foo = "bar"
            __repr__ = make_repr("foo")

        assert repr(Fake()) == "Fake(foo={})".format(repr("bar"))

    def test_with_function(self):
        class Fake:
            foo = "bar"

            def __repr__(self):
                self.__repr__ = make_repr("foo", _self=self)
                return self.__repr__()

        assert repr(Fake()) == "Fake(foo={})".format(repr("bar"))

    def test_with_raise(self):
        class Fake:
            __repr__ = make_repr("foo")

            @property
            def foo(self):
                raise DetachedInstanceError

        assert repr(Fake()) == "Fake(<detached>)"
