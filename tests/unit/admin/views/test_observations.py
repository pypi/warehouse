# SPDX-License-Identifier: Apache-2.0

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
