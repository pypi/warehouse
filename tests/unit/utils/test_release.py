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

from warehouse.utils.release import split_and_strip_keywords


@pytest.mark.parametrize(
    ("keyword_input", "expected"),
    [
        (None, None),
        ("", None),
        ("foo, bar", ["foo", "bar"]),
        ("foo,bar", ["foo", "bar"]),
        ("foo bar baz", ["foo bar baz"]),
        ("foo, bar baz, ", ["foo", "bar baz"]),
        ("foo, bar, baz, ,", ["foo", "bar", "baz"]),
    ],
)
def test_split_and_strip_keywords(keyword_input, expected):
    assert split_and_strip_keywords(keyword_input) == expected
