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

import uuid

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
    def test_change_to_enabled(self, db_request):
        check = MalwareCheckFactory.create(
            name="MyCheck", state=MalwareCheckState.disabled
        )

        db_request.POST = {"id": check.id, "check_state": "enabled"}
        db_request.matchdict["check_name"] = check.name

        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/checks/MyCheck/change_state"
        )

        views.change_check_state(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Changed 'MyCheck' check to 'enabled'!", queue="success")
        ]
        assert check.state == MalwareCheckState.enabled

    def test_change_to_invalid_state(self, db_request):
        check = MalwareCheckFactory.create(name="MyCheck")
        initial_state = check.state
        invalid_check_state = "cancelled"
        db_request.POST = {"id": check.id, "check_state": invalid_check_state}
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

    def test_check_not_found(self, db_request):
        db_request.POST = {"id": uuid.uuid4(), "check_state": "enabled"}
        db_request.matchdict["check_name"] = "DoesNotExist"

        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/checks/DoesNotExist/change_state"
        )

        with pytest.raises(HTTPNotFound):
            views.change_check_state(db_request)
