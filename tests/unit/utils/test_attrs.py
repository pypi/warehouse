# SPDX-License-Identifier: Apache-2.0

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
