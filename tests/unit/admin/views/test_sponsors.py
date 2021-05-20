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

from warehouse.admin.views import sponsors as views
from warehouse.sponsors.models import Sponsor

from ....common.db.sponsors import SponsorFactory


class TestProjectList:
    def test_list_all_sponsors(self, db_request):
        [SponsorFactory.create() for _ in range(5)]
        sponsors = db_request.db.query(Sponsor).order_by(Sponsor.name).all()

        result = views.sponsor_list(db_request)

        assert result == {"sponsors": sponsors}
