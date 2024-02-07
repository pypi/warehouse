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

from collections import defaultdict

import pretend

from warehouse.admin.views import observations as views
from warehouse.observations.models import Observation


class TestObservationsList:
    def test_observations_list(self):
        request = pretend.stub(
            db=pretend.stub(
                query=pretend.call_recorder(
                    lambda *a: pretend.stub(
                        order_by=lambda *a: pretend.stub(all=lambda: [])
                    )
                )
            )
        )
        assert views.observations_list(request) == {"kind_groups": defaultdict(list)}
        assert request.db.query.calls == [pretend.call(Observation)]

    def test_observations_list_with_observations(self):
        observations = [
            Observation(
                kind="is_spam",
                summary="This is spam",
                payload={},
            ),
            Observation(
                kind="is_spam",
                summary="This is also spam",
                payload={},
            ),
        ]

        request = pretend.stub(
            db=pretend.stub(
                query=pretend.call_recorder(
                    lambda *a: pretend.stub(
                        order_by=lambda *a: pretend.stub(all=lambda: observations)
                    )
                )
            )
        )

        assert views.observations_list(request) == {
            "kind_groups": {"is_spam": observations}
        }
        assert request.db.query.calls == [pretend.call(Observation)]
