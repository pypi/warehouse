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

from warehouse.sponsors.models import Sponsor

from ...common.db.sponsors import SponsorFactory


def test_sponsor_color_logo_img_tag(db_request):
    sponsor = SponsorFactory.create()
    expected = f'<img src="{ sponsor.color_logo_url }" alt="{ sponsor.name }">'
    assert sponsor.color_logo_img == expected


def test_sponsor_white_logo_img_tag(db_request):
    sponsor = SponsorFactory.create()
    expected = f'<img class="sponsors__image" src="{ sponsor.white_logo_url }" alt="{ sponsor.name }">'
    assert sponsor.white_logo_img == expected

    # should return empty string if no white logo
    sponsor.white_logo_url = None
    assert sponsor.white_logo_img == ""
