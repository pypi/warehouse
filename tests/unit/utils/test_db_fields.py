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
import pytest

from django import forms

from warehouse.utils.db_fields import (
    CaseInsensitiveCharField, CaseInsensitiveTextField, URLTextField,
)


@pytest.mark.parametrize(("field", "expected"), [
    (CaseInsensitiveCharField, "citext"),
    (CaseInsensitiveTextField, "citext"),
])
def test_db_type(field, expected):
    assert field().db_type(None) == expected


def test_urltextfield_formfield():
    assert isinstance(URLTextField().formfield(), forms.URLField)
