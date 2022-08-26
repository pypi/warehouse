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
from pyramid.security import Allowed

from warehouse.errors import WarehouseDenied
from warehouse.macaroons.caveats import (
    Caveat,
    ExpiryCaveat,
    ProjectIDsCaveat,
    V1Caveat,
    Verifier,
)

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
            ('{"permissions": null, "version": 2}', False),
            ('{"permissions": "user", "version": 2}', False),
            ('{"permissions": "", "version": 2}', False),
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


class TestProjectIDsCaveat:
    @pytest.mark.parametrize(
        "predicate",
        [
            # invalid JSON
            "invalid json",
            # missing project_ids
            '{"missing": "values"}',
            # project_ids present, but null
            '{"project_ids": null}',
            # nbf and exp present, but empty
            '{"project_ids": ""}',
            '{"project_ids": []}',
            # valid JSON, but wrong type
            "[]",
            '""',
        ],
    )
    def test_verify_invalid_predicates(self, predicate):
        verifier = pretend.stub()
        caveat = ProjectIDsCaveat(verifier)

        assert caveat(predicate) is False

    def test_verify_invalid_context(self):
        verifier = pretend.stub(context=pretend.stub())
        caveat = ProjectIDsCaveat(verifier)

        predicate = {"project_ids": ["foo"]}

        assert caveat(json.dumps(predicate)) is False

    def test_verify_invalid_project_id(self, db_request):
        project = ProjectFactory.create(name="foobar")
        verifier = pretend.stub(context=project)
        caveat = ProjectIDsCaveat(verifier)

        predicate = {"project_ids": ["not-foobars-uuid"]}

        assert caveat(json.dumps(predicate)) is False

    def test_verify_ok(self, db_request):
        project = ProjectFactory.create(name="foobar")
        verifier = pretend.stub(context=project)
        caveat = ProjectIDsCaveat(verifier)

        predicate = {"project_ids": [str(project.id)]}

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

    def test_verify_invalid_signature(self, monkeypatch):
        verify = pretend.call_recorder(
            pretend.raiser(MacaroonInvalidSignatureException("Signatures do not match"))
        )
        macaroon = pretend.stub()
        context = pretend.stub()
        principals = pretend.stub()
        permission = pretend.stub()
        key = pretend.stub()
        verifier = Verifier(macaroon, context, principals, permission)

        monkeypatch.setattr(verifier.verifier, "verify", verify)
        status = verifier.verify(key)
        assert not status
        assert status.msg == "Signatures do not match"
        assert verify.calls == [pretend.call(macaroon, key)]

    def test_verify_generic_exception(self, monkeypatch):
        verify = pretend.call_recorder(pretend.raiser(ValueError))
        macaroon = pretend.stub()
        context = pretend.stub()
        principals = pretend.stub()
        permission = pretend.stub()
        key = pretend.stub()
        verifier = Verifier(macaroon, context, principals, permission)

        monkeypatch.setattr(verifier.verifier, "verify", verify)
        status = verifier.verify(key)
        assert not status
        assert status.msg == "malformed macaroon"
        assert verify.calls == [pretend.call(macaroon, key)]

    def test_verify_inner_verifier_returns_false(self, monkeypatch):
        verify = pretend.call_recorder(lambda macaroon, key: False)
        macaroon = pretend.stub()
        context = pretend.stub()
        principals = pretend.stub()
        permission = pretend.stub()
        key = pretend.stub()
        verifier = Verifier(macaroon, context, principals, permission)

        monkeypatch.setattr(verifier.verifier, "verify", verify)
        status = verifier.verify(key)
        assert not status
        assert status.msg == "unknown error"
        assert verify.calls == [pretend.call(macaroon, key)]

    @pytest.mark.parametrize(
        ["caveats", "expected_status"],
        [
            # Both V1 and expiry present and valid.
            (
                [
                    {"permissions": "user", "version": 1},
                    {"exp": int(time.time()) + 3600, "nbf": int(time.time()) - 1},
                ],
                Allowed("signature and caveats OK"),
            ),
            # V1 only present and valid.
            (
                [{"permissions": "user", "version": 1}],
                Allowed("signature and caveats OK"),
            ),
            # V1 and expiry present but V1 invalid.
            (
                [{"permissions": "bad", "version": 1}],
                WarehouseDenied(
                    "invalid permissions format", reason="invalid_api_token"
                ),
            ),
            # V1 and expiry present but expiry invalid.
            (
                [
                    {"permissions": "user", "version": 1},
                    {"exp": int(time.time()) + 1, "nbf": int(time.time()) + 3600},
                ],
                WarehouseDenied("token is expired", reason="invalid_api_token"),
            ),
        ],
    )
    def test_verify(self, monkeypatch, caveats, expected_status):
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
        status = verifier.verify(key)
        assert bool(status) is bool(expected_status)
        assert status.msg == expected_status.msg
