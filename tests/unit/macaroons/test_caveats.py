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

from warehouse.macaroons.caveats import (
    Caveat,
    InvalidMacaroonError,
    TopLevelCaveat,
    V1Caveat,
    V2Caveat,
    Verifier,
)

from ...common.db.packaging import ProjectFactory


class TestCaveat:
    def test_creation(self):
        verifier = pretend.stub()
        caveat = Caveat(verifier)

        assert caveat.verifier is verifier
        with pytest.raises(InvalidMacaroonError):
            caveat.verify(pretend.stub())
        with pytest.raises(InvalidMacaroonError):
            caveat(pretend.stub())


class TestV1Caveat:
    @pytest.mark.parametrize(
        "predicate",
        [
            # Wrong version
            {"version": 2},
            # Right version, missing permissions
            {"version": 1},
            # Right version, permissions are empty
            {"permissions": None, "version": 1},
            {"permissions": {}, "version": 1},
            # Right version, missing projects list
            {"permissions": {"projects": None}, "version": 1},
        ],
    )
    def test_verify_invalid_predicates(self, predicate):
        verifier = pretend.stub()
        caveat = V1Caveat(verifier)

        with pytest.raises(InvalidMacaroonError):
            caveat(predicate)

    def test_verify_valid_predicate(self):
        verifier = pretend.stub()
        caveat = V1Caveat(verifier)
        predicate = {"permissions": "user", "version": 1}

        assert caveat(predicate) is True

    def test_verify_project_invalid_context(self):
        verifier = pretend.stub(context=pretend.stub())
        caveat = V1Caveat(verifier)

        predicate = {"version": 1, "permissions": {"projects": ["notfoobar"]}}
        with pytest.raises(InvalidMacaroonError):
            caveat(predicate)

    def test_verify_project_invalid_project_name(self, db_request):
        project = ProjectFactory.create(name="foobar")
        verifier = pretend.stub(context=project)
        caveat = V1Caveat(verifier)

        predicate = {"version": 1, "permissions": {"projects": ["notfoobar"]}}
        with pytest.raises(InvalidMacaroonError):
            caveat(predicate)

    def test_verify_project_no_projects_object(self, db_request):
        project = ProjectFactory.create(name="foobar")
        verifier = pretend.stub(context=project)
        caveat = V1Caveat(verifier)

        predicate = {
            "version": 1,
            "permissions": {"somethingthatisntprojects": ["blah"]},
        }
        with pytest.raises(InvalidMacaroonError):
            caveat(predicate)

    def test_verify_project(self, db_request):
        project = ProjectFactory.create(name="foobar")
        verifier = pretend.stub(context=project)
        caveat = V1Caveat(verifier)

        predicate = {"version": 1, "permissions": {"projects": ["foobar"]}}
        assert caveat(predicate) is True


class TestV2Caveat:
    @pytest.mark.parametrize(
        "predicate",
        [
            # Wrong version
            {"version": 1},
            # Right version, no contents
            {"version": 2},
        ],
    )
    def test_verify_invalid_predicates(self, predicate):
        verifier = pretend.stub()
        caveat = V2Caveat(verifier)

        with pytest.raises(InvalidMacaroonError):
            caveat(predicate)

    def test_verify(self):
        verifier = pretend.stub()
        caveat = V2Caveat(verifier)

        # TODO: Nothing to test yet.
        predicate = {"version": 2}
        with pytest.raises(InvalidMacaroonError):
            caveat(predicate)


class TestTopLevelCaveat:
    @pytest.mark.parametrize(
        "predicate",
        [
            # Completely invalid (missing payloads, invalid types, invalid JSON)
            {},
            '""',
            [],
            None,
            "invalid json",
            # Empty version
            {"version": None},
            # Unsupported versions
            {"version": 0},
            {"version": 3},
        ],
    )
    def test_verify_bad_versions(self, predicate):
        verifier = pretend.stub()
        caveat = TopLevelCaveat(verifier)

        assert caveat.verifier is verifier

        with pytest.raises(InvalidMacaroonError):
            caveat(json.dumps(predicate))

    def test_verify_dispatch_v1(self, monkeypatch):
        verifier = pretend.stub()
        caveat = TopLevelCaveat(verifier)

        v1_verify = pretend.call_recorder(lambda self, predicate: True)
        v2_verify = pretend.call_recorder(lambda self, predicate: True)
        monkeypatch.setattr(V1Caveat, "verify", v1_verify)
        monkeypatch.setattr(V2Caveat, "verify", v2_verify)

        predicate = {"version": 1}
        caveat(json.dumps(predicate))

        assert len(v1_verify.calls) == 1
        assert len(v2_verify.calls) == 0

    def test_verify_dispatch_v2(self, monkeypatch):
        verifier = pretend.stub()
        caveat = TopLevelCaveat(verifier)

        v1_verify = pretend.call_recorder(lambda self, predicate: True)
        v2_verify = pretend.call_recorder(lambda self, predicate: True)
        monkeypatch.setattr(V1Caveat, "verify", v1_verify)
        monkeypatch.setattr(V2Caveat, "verify", v2_verify)

        predicate = {"version": 2}
        caveat(json.dumps(predicate))

        assert len(v1_verify.calls) == 0
        assert len(v2_verify.calls) == 1


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

    def test_verify(self, monkeypatch):
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
        with pytest.raises(InvalidMacaroonError):
            verifier.verify(key)
        assert verify.calls == [pretend.call(macaroon, key)]
