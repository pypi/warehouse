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

import json

import pretend
import pytest

from pymacaroons.exceptions import MacaroonInvalidSignatureException

from warehouse.macaroons.caveats import Caveat, InvalidMacaroon, V1Caveat, Verifier

from ...common.db.packaging import ProjectFactory


class TestCaveat:
    def test_creation(self):
        verifier = pretend.stub()
        caveat = Caveat(verifier)

        assert caveat.verifier is verifier
        assert caveat.verify(pretend.stub()) is False
        assert caveat(pretend.stub()) is False


class TestV1Caveat:
    @pytest.mark.parametrize(
        ["predicate", "result"],
        [
            ("invalid json", False),
            ('{"version": 2}', False),
            ('{"permissions": null, "version": 1}', False),
        ],
    )
    def test_verify_invalid_predicates(self, predicate, result):
        verifier = pretend.stub()
        caveat = V1Caveat(verifier)

        assert caveat(predicate) is False

    def test_verify_valid_predicate(self):
        verifier = pretend.stub()
        caveat = V1Caveat(verifier)
        predicate = '{"permissions": "user", "version": 1}'

        assert caveat(predicate) is True

    def test_verify_project_invalid_context(self):
        verifier = pretend.stub(context=pretend.stub())
        caveat = V1Caveat(verifier)

        predicate = {"version": 1, "permissions": {"projects": ["notfoobar"]}}

        assert caveat(json.dumps(predicate)) is False

    def test_verify_project_invalid_project_name(self, db_request):
        project = ProjectFactory.create(name="foobar")
        verifier = pretend.stub(context=project)
        caveat = V1Caveat(verifier)

        predicate = {"version": 1, "permissions": {"projects": ["notfoobar"]}}

        assert caveat(json.dumps(predicate)) is False

    def test_verify_project_no_projects_object(self, db_request):
        project = ProjectFactory.create(name="foobar")
        verifier = pretend.stub(context=project)
        caveat = V1Caveat(verifier)

        predicate = {
            "version": 1,
            "permissions": {"somethingthatisntprojects": ["blah"]},
        }
        assert caveat(json.dumps(predicate)) is False

    def test_verify_project(self, db_request):
        project = ProjectFactory.create(name="foobar")
        verifier = pretend.stub(context=project)
        caveat = V1Caveat(verifier)
        predicate = {"version": 1, "permissions": {"projects": ["foobar"]}}

        assert caveat(json.dumps(predicate)) is True


class TestVerifier:
    def test_creation(self):
        macaroon = pretend.stub()
        context = pretend.stub()
        principals = pretend.stub()
        permission = pretend.stub()
        verifier = Verifier(macaroon, context, principals, permission)

        assert verifier.macaroon is macaroon
        assert verifier.context is context
        assert verifier.principals is principals
        assert verifier.permission is permission

    def test_verify_raises(self, monkeypatch):
        verify = pretend.call_recorder(
            pretend.raiser(MacaroonInvalidSignatureException)
        )
        macaroon = pretend.stub()
        context = pretend.stub()
        principals = pretend.stub()
        permission = pretend.stub()
        key = pretend.stub()
        verifier = Verifier(macaroon, context, principals, permission)

        monkeypatch.setattr(verifier.verifier, "verify", verify)
        with pytest.raises(InvalidMacaroon):
            verifier.verify(key)
        assert verify.calls == [pretend.call(macaroon, key)]

    def test_verify_works(self, monkeypatch):
        verify = pretend.call_recorder(lambda x, y: True)
        macaroon = pretend.stub()
        context = pretend.stub()
        principals = pretend.stub()
        permission = pretend.stub()
        key = pretend.stub()
        verifier = Verifier(macaroon, context, principals, permission)

        monkeypatch.setattr(verifier.verifier, "verify", verify)

        verifier.verify(key)
        assert verify.calls == [pretend.call(macaroon, key)]

    def test_verify_false(self, monkeypatch):
        # This will not happen in real life, but in case pymacaroon's verify returns
        # False, we need to raise.
        verify = pretend.call_recorder(lambda x, y: False)
        macaroon = pretend.stub()
        context = pretend.stub()
        principals = pretend.stub()
        permission = pretend.stub()
        key = pretend.stub()
        verifier = Verifier(macaroon, context, principals, permission)

        monkeypatch.setattr(verifier.verifier, "verify", verify)

        with pytest.raises(InvalidMacaroon):
            verifier.verify(key)
