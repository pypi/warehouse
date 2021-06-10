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

from ...common.db.banners import BannerFactory


def test_banner_is_live_property(db_request):
    today = date.today()
    ten_days = timedelta(days=10)

    banner = BannerFactory.create()
    assert banner.begin < today < banner.end
    assert banner.is_live is True

    # banner from the past
    banner.begin = today - (ten_days * 2)
    banner.end = today - ten_days
    assert banner.is_live is False

    # banner in the future
    banner.begin = today + ten_days
    banner.end = today + (ten_days * 2)
    assert banner.is_live is False
