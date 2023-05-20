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

from warehouse.banners import views

from ...common.db.banners import BannerFactory


def test_list_active_banners(db_request):
    active_banner = BannerFactory.create()
    assert active_banner.is_live
    inactive_banner = BannerFactory.create(active=False)
    assert inactive_banner.is_live is False

    result = views.list_banner_messages(db_request)

    assert result["banners"] == [active_banner]


def test_list_specific_banner_for_preview(db_request):
    active_banner = BannerFactory.create()
    assert active_banner.is_live
    inactive_banner = BannerFactory.create(active=False)
    assert inactive_banner.is_live is False

    db_request.params = {"single_banner": str(inactive_banner.id)}
    result = views.list_banner_messages(db_request)

    assert result["banners"] == [inactive_banner]
