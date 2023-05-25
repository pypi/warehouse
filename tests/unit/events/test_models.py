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

from warehouse.events.models import GeoIPInfo


class TestGeoIPInfo:
    @pytest.mark.parametrize(
        "test_input, expected",
        [
            ({}, ""),
            (
                {"city": "new york", "country_code": "us", "region": "ny"},
                "New York, NY, US",
            ),
            (
                {"city": "new york", "country_code": "us"},
                "New York, US",
            ),
            ({"city": "new york", "region": "ny"}, "New York, NY"),
            ({"region": "ny", "country_code": "us"}, "NY, US"),
            ({"country_name": "United States"}, "United States"),
        ],
    )
    def test_display_output(self, test_input, expected):
        """Create a GeoIPInfo object and test the display method."""
        dataklazz = GeoIPInfo(**test_input)
        assert dataklazz.display() == expected
