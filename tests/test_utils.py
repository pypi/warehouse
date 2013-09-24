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

import pytest

from warehouse.utils import AttributeDict, convert_to_attr_dict, merge_dict


def test_basic_attribute_dict_access():
    adict = AttributeDict({
        "foo": None,
        "bar": "Success!"
    })

    assert adict.foo is adict["foo"]
    assert adict.bar is adict["bar"]


def test_attribute_dict_unknown_access():
    adict = AttributeDict()

    with pytest.raises(AttributeError):
        adict.unknown


@pytest.mark.parametrize(("base", "additional", "expected"), [
    ({"a": 1}, {"a": 2}, {"a": 2}),
    ({"a": 1}, {"b": 2}, {"a": 1, "b": 2}),
    ({"a": 1, "b": 2}, {"b": 3, "c": 4}, {"a": 1, "b": 3, "c": 4}),
    (None, {"a": 2}, {"a": 2}),
    ({"a": 1}, None, {"a": 1}),
    ("Test", {"a": 7}, {"a": 7}),
    ({"a": 9}, "Test", "Test"),
    ({"a": {"b": 3}}, {"a": {"b": 7, "c": 0}}, {"a": {"b": 7, "c": 0}}),
])
def test_merge_dictionary(base, additional, expected):
    assert merge_dict(base, additional) == expected


def test_convert_to_attribute_dict():
    adict = convert_to_attr_dict({"a": {"b": 1, "c": 2}})

    assert adict.a == {"b": 1, "c": 2}
    assert adict.a.b == 1
    assert adict.a.c == 2
