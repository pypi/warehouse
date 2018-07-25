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

from warehouse.credits import views

from ...common.db.contributors import ContributorFactory


class TestCredits:
    def test_credits_page(self, db_request):

        contrib = [
            ContributorFactory.create(),
            ContributorFactory.create(),
            ContributorFactory.create(),
        ]

        db_request.contributors = pretend.call_recorder(lambda contributors: contrib)

        resp = views.credits_page(db_request)
        assert isinstance(resp["contributors"], list)
