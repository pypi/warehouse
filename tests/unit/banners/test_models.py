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
    ("begin_diff", "end_diff", "expected"),
    [
        (-20, -10, False),  # past banner (started 20 days ago, ended 10)
        (10, 20, False),  # future banner (starts in 10 days, ends in 20)
        (-5, 5, True),  # live banner (started 5 days ago, ends in 5)
    ],
)
def test_banner_is_live_property(db_request, begin_diff, end_diff, expected):
    today = date.today()
    banner = Banner()

    banner.begin = today + timedelta(days=begin_diff)
    banner.end = today + timedelta(days=end_diff)
    assert banner.is_live is expected
