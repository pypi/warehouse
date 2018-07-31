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

from warehouse.credits import views

from ...common.db.contributors import ContributorFactory


class TestCredits:
    @pytest.mark.parametrize("contrib_length", [2, 3])
    def test_credits_page(self, db_request, contrib_length):

        contrib = []

        for _ in range(contrib_length):
            contrib.append(ContributorFactory.create())

        db_request.contributors = pretend.call_recorder(lambda contributors: contrib)

        resp = views.credits_page(db_request)
        assert isinstance(resp["contributors"], list)
