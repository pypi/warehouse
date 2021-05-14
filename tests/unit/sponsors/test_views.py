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

import pretend
import pytest

from warehouse.sponsors import views
from warehouse.sponsors.models import Sponsor

from ...common.db.sponsors import SponsorFactory


class TestSponsorsPage:
    def test_list_sponsors(self, db_request):
        sponsors = [SponsorFactory.create() for i in range(3)]

        result = views.display_sponsors_page(db_request)

        expected = db_request.db.query(Sponsor).all()
        assert result == {"sponsors": expected}
