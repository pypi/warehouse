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
import os
import time

import pretend
import pymacaroons
import pytest

from pymacaroons.exceptions import MacaroonInvalidSignatureException

from warehouse.macaroons.caveats import Caveat, ExpiryCaveat, V1Caveat, Verifier

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


class TestExpiryCaveat:
    @pytest.mark.parametrize(
        "predicate",
        [
            # invalid JSON
            "invalid json",
            # missing nbf and exp
            '{"missing": "values"}',
            # nbf and exp present, but null
            '{"nbf": null, "exp": null}',
            # nbf and exp present, but empty
            '{"nbf": "", "exp": ""}',
            # valid JSON, but wrong type
            "[]",
        ],
    )
    def test_verify_invalid_predicates(self, predicate):
        verifier = pretend.stub()
        caveat = ExpiryCaveat(verifier)

        assert caveat(predicate) is False

    def test_verify_not_before(self):
        verifier = pretend.stub()
        caveat = ExpiryCaveat(verifier)

        not_before = int(time.time()) + 60
        expiry = not_before + 60
        predicate = json.dumps({"exp": expiry, "nbf": not_before})
        assert caveat(predicate) is False

    def test_verify_already_expired(self):
        verifier = pretend.stub()
        caveat = ExpiryCaveat(verifier)

        not_before = int(time.time()) - 10
        expiry = not_before - 5
        predicate = json.dumps({"exp": expiry, "nbf": not_before})
        assert caveat(predicate) is False

    def test_verify_ok(self):
        verifier = pretend.stub()
        caveat = ExpiryCaveat(verifier)

        not_before = int(time.time()) - 10
        expiry = int(time.time()) + 60
        predicate = json.dumps({"exp": expiry, "nbf": not_before})
        assert caveat(predicate)


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

    def test_verify_invalid_signature(self, monkeypatch):
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
        assert verifier.verify(key) is False
        assert verify.calls == [pretend.call(macaroon, key)]

    @pytest.mark.parametrize(
        ["caveats", "valid"],
        [
            # Both V1 and expiry present and valid.
            (
                [
                    {"permissions": "user", "version": 1},
                    {"exp": int(time.time()) + 3600, "nbf": int(time.time()) - 1},
                ],
                True,
            ),
            # V1 only present and valid.
            ([{"permissions": "user", "version": 1}], True),
            # V1 and expiry present but V1 invalid.
            ([{"permissions": "bad", "version": 1}], False),
            # V1 and expiry present but expiry invalid.
            (
                [
                    {"permissions": "user", "version": 1},
                    {"exp": int(time.time()) + 1, "nbf": int(time.time()) + 3600},
                ],
                False,
            ),
        ],
    )
    def test_verify(self, monkeypatch, caveats, valid):
        key = os.urandom(32)
        m = pymacaroons.Macaroon(
            location="fakelocation",
            identifier="fakeid",
            key=key,
            version=pymacaroons.MACAROON_V2,
        )

        for caveat in caveats:
            m.add_first_party_caveat(json.dumps(caveat))

        # Round-trip through serialization to ensure we're not clinging to any state.
        serialized_macaroon = m.serialize()
        deserialized_macaroon = pymacaroons.Macaroon.deserialize(serialized_macaroon)

        context = pretend.stub()
        principals = pretend.stub()
        permission = pretend.stub()

        verifier = Verifier(deserialized_macaroon, context, principals, permission)
        assert verifier.verify(key) is valid
