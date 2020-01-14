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

from pyramid.httpexceptions import HTTPNotFound

from warehouse.admin.views import checks as views
from warehouse.malware.models import MalwareCheckState

from ....common.db.malware import MalwareCheckFactory


class TestListChecks:
    def test_get_checks_none(self, db_request):
        assert views.get_checks(db_request) == {"checks": []}

    def test_get_checks(self, db_request):
        checks = [MalwareCheckFactory.create() for _ in range(10)]
        assert views.get_checks(db_request) == {"checks": checks}

    def test_get_checks_different_versions(self, db_request):
        checks = [MalwareCheckFactory.create() for _ in range(5)]
        checks_same = [
            MalwareCheckFactory.create(name="MyCheck", version=i) for i in range(1, 6)
        ]
        checks.append(checks_same[-1])
        assert views.get_checks(db_request) == {"checks": checks}


class TestGetCheck:
    def test_get_check(self, db_request):
        check = MalwareCheckFactory.create()
        db_request.matchdict["check_name"] = check.name
        assert views.get_check(db_request) == {
            "check": check,
            "checks": [check],
            "states": MalwareCheckState,
        }

    def test_get_check_many_versions(self, db_request):
        check1 = MalwareCheckFactory.create(name="MyCheck", version="1")
        check2 = MalwareCheckFactory.create(name="MyCheck", version="2")
        db_request.matchdict["check_name"] = check1.name
        assert views.get_check(db_request) == {
            "check": check2,
            "checks": [check2, check1],
            "states": MalwareCheckState,
        }

    def test_get_check_not_found(self, db_request):
        db_request.matchdict["check_name"] = "DoesNotExist"
        with pytest.raises(HTTPNotFound):
            views.get_check(db_request)


class TestChangeCheckState:
    def test_no_check_state(self, db_request):
        check = MalwareCheckFactory.create()
        db_request.matchdict["check_name"] = check.name
        with pytest.raises(HTTPNotFound):
            views.change_check_state(db_request)

    @pytest.mark.parametrize(
        ("final_state"), [MalwareCheckState.disabled, MalwareCheckState.wiped_out]
    )
    def test_change_to_valid_state(self, db_request, final_state):
        check = MalwareCheckFactory.create(
            name="MyCheck", state=MalwareCheckState.disabled
        )

        db_request.POST = {"check_state": final_state.value}
        db_request.matchdict["check_name"] = check.name

        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        wipe_out_recorder = pretend.stub(
            delay=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.task = pretend.call_recorder(lambda *a, **kw: wipe_out_recorder)

        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/checks/MyCheck/change_state"
        )

        views.change_check_state(db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                "Changed 'MyCheck' check to '%s'!" % final_state.value, queue="success"
            )
        ]

        assert check.state == final_state

        if final_state == MalwareCheckState.wiped_out:
            assert wipe_out_recorder.delay.calls == [pretend.call("MyCheck")]

    def test_change_to_invalid_state(self, db_request):
        check = MalwareCheckFactory.create(name="MyCheck")
        initial_state = check.state
        invalid_check_state = "cancelled"
        db_request.POST = {"check_state": invalid_check_state}
        db_request.matchdict["check_name"] = check.name

        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/checks/MyCheck/change_state"
        )

        views.change_check_state(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Invalid check state provided.", queue="error")
        ]
        assert check.state == initial_state


class TestRunBackfill:
    @pytest.mark.parametrize(("sample_rate"), [None, "abc"])
    def test_invalid_form_values(self, db_request, sample_rate):
        check = MalwareCheckFactory.create()
        db_request.matchdict["check_name"] = check.name

        if sample_rate:
            db_request.POST["sample-rate"] = sample_rate

        with pytest.raises(HTTPNotFound):
            views.run_backfill(db_request)

    @pytest.mark.parametrize(
        ("check_state", "sample_rate", "message"),
        [
            (
                MalwareCheckState.disabled,
                1,
                "Check must be in 'enabled' or 'evaluation' state to run a backfill.",
            ),
            (
                MalwareCheckState.wiped_out,
                1,
                "Check must be in 'enabled' or 'evaluation' state to run a backfill.",
            ),
            (
                MalwareCheckState.enabled,
                -1,
                "Sample percentage must be an integer between 0 and 100.",
            ),
            (
                MalwareCheckState.evaluation,
                0,
                "Sample percentage must be an integer between 0 and 100.",
            ),
            (
                MalwareCheckState.enabled,
                101,
                "Sample percentage must be an integer between 0 and 100.",
            ),
        ],
    )
    def test_invalid_backfill_parameters(
        self, db_request, check_state, sample_rate, message
    ):
        check = MalwareCheckFactory.create(state=check_state)
        db_request.matchdict["check_name"] = check.name
        db_request.POST["sample-rate"] = sample_rate

        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/checks/%s/run_backfill" % check.name
        )

        views.run_backfill(db_request)

        assert db_request.session.flash.calls == [pretend.call(message, queue="error")]

    def test_sucess(self, db_request):
        check = MalwareCheckFactory.create(state=MalwareCheckState.enabled)
        db_request.matchdict["check_name"] = check.name
        db_request.POST["sample-rate"] = "1"

        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/checks/%s/run_backfill" % check.name
        )

        backfill_recorder = pretend.stub(
            delay=pretend.call_recorder(lambda *a, **kw: None)
        )

        db_request.task = pretend.call_recorder(lambda *a, **kw: backfill_recorder)

        views.run_backfill(db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                "Running '%s' on 1%% of all '%s's!"
                % (check.name, check.hooked_object.value),
                queue="success",
            )
        ]

        assert backfill_recorder.delay.calls == [pretend.call(check.name, 0.01)]
