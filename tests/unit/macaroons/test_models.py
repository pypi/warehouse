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

from warehouse.macaroons import caveats, models


def test_generate_key():
    key = models._generate_key()

    assert isinstance(key, bytes)
    assert len(key) == 32


class TestCaveats:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (
                [
                    caveats.ProjectName(normalized_names=["example"]),
                    caveats.Expiration(expires_at=1705876828, not_before=1705875828),
                ],
                [[1, ["example"]], [0, 1705876828, 1705875828]],
            ),
            ([], []),
        ],
    )
    def test_serialization(self, value, expected):
        dm = models.Macaroon()
        dm.caveats = value
        assert dm._caveats == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (
                [[3, "a614e122-a9ee-473c-b6df-8c4f1b776628"], [1, ["foo", "bar"]]],
                [
                    caveats.RequestUser(user_id="a614e122-a9ee-473c-b6df-8c4f1b776628"),
                    caveats.ProjectName(normalized_names=["foo", "bar"]),
                ],
            ),
            ([], []),
        ],
    )
    def test_deserialization(self, value, expected):
        dm = models.Macaroon()
        dm._caveats = value
        assert dm.caveats == expected
