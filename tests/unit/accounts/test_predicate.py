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

from pyramid.exceptions import ConfigurationError

import pretend
import pytest
from warehouse.accounts.predicates import HeadersPredicate


class TestHeadersPredicate:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (["Foo", "Bar"], "header Foo, header Bar"),
            (["Foo", "Bar:baz"], "header Foo, header Bar=baz"),
        ],
    )
    def test_text(self, value, expected):
        predicate = HeadersPredicate(value, None)
        assert predicate.text() == expected
        assert predicate.phash() == expected

    def test_when_empty(self):
        with pytest.raises(ConfigurationError):
            HeadersPredicate([], None)

    @pytest.mark.parametrize(
        "value", [["Foo", "Bar"], ["Foo", "Bar:baz"]],
    )
    def test_valid_value(self, value):
        predicate = HeadersPredicate(value, None)
        assert predicate(None, pretend.stub(headers={"Foo": "a", "Bar": "baz"}))

    @pytest.mark.parametrize(
        "value", [["Foo", "Baz"], ["Foo", "Bar:foo"]],
    )
    def test_invalid_value(self, value):
        predicate = HeadersPredicate(value, None)
        assert not predicate(None, pretend.stub(headers={"Foo": "a", "Bar": "baz"}))
