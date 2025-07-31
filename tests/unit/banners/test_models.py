# SPDX-License-Identifier: Apache-2.0

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
