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
from datetime import date, timedelta

import pytest

from warehouse.banners.models import Banner


@pytest.mark.parametrize(
    ("active", "end_diff", "expected"),
    [
        (False, -10, False),  # past inactive banner (ended 10 days ago)
        (True, -10, False),  # past active banner using end date as safeguard
        (False, 20, False),  # future inactive banner (ends in 20 days)
        (True, 20, True),  # future active banner (ends in 20 days)
    ],
)
def test_banner_is_live_property(db_request, active, end_diff, expected):
    banner = Banner()
    banner.active = active
    banner.end = date.today() + timedelta(days=end_diff)
    assert banner.is_live is expected
