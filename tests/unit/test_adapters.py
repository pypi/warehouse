import pytest

from warehouse.adapters import BaseAdapter


def test_adapter_contributes():
    class Foo(object):
        pass

    adapter = BaseAdapter()
    adapter.contribute_to_class(Foo, "api")

    assert Foo.api is adapter


def test_adapter_not_instances():
    class Foo(object):
        pass

    adapter = BaseAdapter()
    adapter.contribute_to_class(Foo, "api")

    # Make sure this doesn't raise an exception
    Foo.api

    # Make sure this does raise an exception
    with pytest.raises(AttributeError):
        Foo().api
