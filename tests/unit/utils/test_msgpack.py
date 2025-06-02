# SPDX-License-Identifier: Apache-2.0

from warehouse.i18n import LazyString
from warehouse.utils.msgpack import object_encode


def test_object_encode_passes_through():
    assert object_encode("foo") == "foo"


def test_object_encode_converts_lazystring():
    def stringify(*args, **kwargs):
        return "foo"

    ls = LazyString(stringify, "foobar")
    assert object_encode(ls) == "foo"
