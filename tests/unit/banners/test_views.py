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

from warehouse.banners import views

from ...common.db.banners import BannerFactory


def test_list_active_banners(db_request):
    today = date.today()
    ten_days = timedelta(days=10)

    active_baner = BannerFactory.create()
    # past banner
    BannerFactory.create(
        begin=today - (ten_days * 2),
        end=today - ten_days,
    )
    # future banner
    BannerFactory.create(
        begin=today + ten_days,
        end=today + (ten_days * 2),
    )

    result = views.list_banner_messages(db_request)

    assert len(result["banners"]) == 1
    assert result["banners"][0] == active_baner


def test_list_specific_banner_for_preview(db_request):
    today = date.today()
    ten_days = timedelta(days=10)

    BannerFactory.create()  # active banner
    # past banner
    past_banner = BannerFactory.create(
        begin=today - (ten_days * 2),
        end=today - ten_days,
    )

    db_request.params = {"single_banner": str(past_banner.id)}
    result = views.list_banner_messages(db_request)

    assert len(result["banners"]) == 1
    assert result["banners"][0] == past_banner
