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
from unittest import TestCase

from warehouse.admin.views import banners as views
from warehouse.banners.models import Banner

from ....common.db.banners import BannerFactory


class TestBannerList:
    def test_list_all_banners(self, db_request):
        [BannerFactory.create() for _ in range(5)]
        banners = db_request.db.query(Banner).order_by(Banner.begin.desc()).all()

        result = views.banner_list(db_request)

        assert result == {"banners": banners}


class TestBannerForm(TestCase):
    def setUp(self):
        self.data = {
            "name": "Sample Banner",
            "text": "This should be the correct text",
            "link_url": "https://samplebanner.com",
            "begin": "2021-06-30",
            "end": "2021-07-30",
        }

    def test_required_fields(self):
        required_fields = self.data.keys()  # all fields are required

        form = views.BannerForm(data={})

        assert form.validate() is False
        assert len(form.errors) == len(required_fields)
        for field in required_fields:
            assert field in form.errors

    def test_valid_data(self):
        form = views.BannerForm(data=self.data)
        assert form.validate() is True

    def test_invalid_form_if_wrong_time_interval(self):
        self.data["begin"], self.data["end"] = self.data["end"], self.data["begin"]

        form = views.BannerForm(data=self.data)

        assert form.validate() is False
        assert "begin" in form.errors
        assert "end" in form.errors
