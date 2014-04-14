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
import pytest

from warehouse.datastructures import AttributeDict


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


def test_convert_to_attribute_dict():
    adict = AttributeDict({"a": {"b": 1, "c": 2}})

    assert adict.a == {"b": 1, "c": 2}
    assert adict.a.b == 1
    assert adict.a.c == 2
