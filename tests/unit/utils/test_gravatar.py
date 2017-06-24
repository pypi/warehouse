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

from warehouse.utils.gravatar import gravatar, profile


@pytest.mark.parametrize(
    ("email", "size", "expected"),
    [
        (
            None,
            None,
            "https://secure.gravatar.com/avatar/"
            "d41d8cd98f00b204e9800998ecf8427e?size=80",
        ),
        (
            None,
            50,
            "https://secure.gravatar.com/avatar/"
            "d41d8cd98f00b204e9800998ecf8427e?size=50",
        ),
        (
            "",
            None,
            "https://secure.gravatar.com/avatar/"
            "d41d8cd98f00b204e9800998ecf8427e?size=80",
        ),
        (
            "",
            40,
            "https://secure.gravatar.com/avatar/"
            "d41d8cd98f00b204e9800998ecf8427e?size=40",
        ),
        (
            "foo@example.com",
            None,
            "https://secure.gravatar.com/avatar/"
            "b48def645758b95537d4424c84d1a9ff?size=80",
        ),
        (
            "foo@example.com",
            100,
            "https://secure.gravatar.com/avatar/"
            "b48def645758b95537d4424c84d1a9ff?size=100",
        ),
    ],
)
def test_gravatar(email, size, expected):
    kwargs = {}
    if size is not None:
        kwargs["size"] = size
    assert gravatar(email, **kwargs) == expected


def test_profile():
    email = "foo@example.com"
    expected = "https://gravatar.com/b48def645758b95537d4424c84d1a9ff"
    assert profile(email) == expected
