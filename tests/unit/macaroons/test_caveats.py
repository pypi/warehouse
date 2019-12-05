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

from datetime import datetime, timezone

import pretend
import pytest

from pymacaroons.exceptions import MacaroonInvalidSignatureException

from warehouse.macaroons.caveats import (
    Caveat,
    InvalidMacaroon,
    TopLevelCaveat,
    V1Caveat,
    V2Caveat,
    Verifier,
)

from ...common.db.packaging import ProjectFactory, ReleaseFactory


class TestCaveat:
    def test_creation(self):
        verifier = pretend.stub()
        caveat = Caveat(verifier)

        assert caveat.verifier is verifier
        with pytest.raises(InvalidMacaroon):
            caveat.verify(pretend.stub())
        with pytest.raises(InvalidMacaroon):
            caveat(pretend.stub())


class TestV1Caveat:
    @pytest.mark.parametrize(
        ["predicate", "valid"],
        [
            ("invalid json", False),
            ("", False),
            ("{}", False),
            ('{"version": 1, "permissions": "user"}', True),
            ('{"version": 1}', False),
            ('{"version": 2, "permissions": "user"}', True),
            ('{"version": 2}', False),
            ('{"version": 3}', False),
        ],
    )
    def test_verify_toplevel_caveat(self, monkeypatch, predicate, valid):
        verifier = pretend.stub()
        caveat = TopLevelCaveat(verifier)

        if not valid:
            with pytest.raises(InvalidMacaroon):
                caveat(predicate)
        else:
            assert caveat(predicate)

    @pytest.mark.parametrize(
        "predicate", [{}, {"permissions": None}, {"permissions": {"projects": None}}]
    )
    def test_verify_invalid_v1_predicates(self, predicate):
        verifier = pretend.stub()
        caveat = V1Caveat(verifier)

        with pytest.raises(InvalidMacaroon):
            caveat(predicate)

    @pytest.mark.parametrize(
        "predicate",
        [
            {"version": 1, "permissions": {"projects": ["foobar"]}},
            {"version": 1, "permissions": "user"},
        ],
    )
    def test_verify_valid_v1_predicates(self, db_request, predicate):
        project = ProjectFactory.create(name="foobar")
        verifier = pretend.stub(context=project)
        caveat = V1Caveat(verifier)

        caveat(predicate)

    @pytest.mark.parametrize(
        "predicate",
        [
            {"version": 1, "permissions": {"projects": ["notfoobar"]}},
            {"version": 2, "permissions": {"projects": [{"name": "notfoobar"}]}},
        ],
    )
    def test_verify_project_invalid_context(self, predicate):
        verifier = pretend.stub(context=pretend.stub())

        if predicate["version"] == 1:
            caveat = V1Caveat(verifier)
        else:
            caveat = V2Caveat(verifier)

        with pytest.raises(InvalidMacaroon):
            caveat(predicate)

    @pytest.mark.parametrize(
        ["predicate", "valid"],
        [
            ({"version": 2, "expiration": 0, "permissions": "user"}, False),
            (
                {
                    "version": 2,
                    "expiration": int(datetime.now(tz=timezone.utc).timestamp()) + 3600,
                    "permissions": "user",
                },
                True,
            ),
        ],
    )
    def test_verify_v2_caveat_expiration(self, predicate, valid):
        verifier = pretend.stub()
        caveat = V2Caveat(verifier)

        if not valid:
            with pytest.raises(InvalidMacaroon):
                caveat(predicate)
        else:
            assert caveat(predicate)

    @pytest.mark.parametrize(
        ["predicate", "valid"],
        [
            (
                {
                    "version": 2,
                    "permissions": {"projects": [{"name": "foo", "version": "1.0.0"}]},
                },
                False,
            ),
            (
                {
                    "version": 2,
                    "permissions": {"projects": [{"name": "foo", "version": "1.0.1"}]},
                },
                True,
            ),
        ],
    )
    def test_verify_v2_caveat_release(self, db_request, predicate, valid):
        project = ProjectFactory.create(name="foo")
        ReleaseFactory.create(project=project, version="1.0.0")

        verifier = pretend.stub(context=project)
        caveat = V2Caveat(verifier)

        if not valid:
            with pytest.raises(InvalidMacaroon):
                caveat(predicate)
        else:
            assert caveat(predicate)

    @pytest.mark.parametrize(
        ["predicate", "valid"],
        [
            ({"version": 2, "permissions": {"projects": [{"name": "foo"}]}}, False),
            ({"version": 2, "permissions": {}}, False),
            ({"version": 2, "permissions": {"projects": [{"name": "bar"}]}}, True),
        ],
    )
    def test_verify_v2_caveat_project(self, db_request, predicate, valid):
        project = ProjectFactory.create(name="bar")
        verifier = pretend.stub(context=project)
        caveat = V2Caveat(verifier)

        if not valid:
            with pytest.raises(InvalidMacaroon):
                caveat(predicate)
        else:
            assert caveat(predicate)

    @pytest.mark.parametrize(
        "predicate",
        [
            {"version": 1, "permissions": {"projects": ["notfoobar"]}},
            {"version": 2, "permissions": {"projects": [{"name": "notfoobar"}]}},
        ],
    )
    def test_verify_project_invalid_project_name(self, db_request, predicate):
        project = ProjectFactory.create(name="foobar")
        verifier = pretend.stub(context=project)

        if predicate["version"] == 1:
            caveat = V1Caveat(verifier)
        else:
            caveat = V2Caveat(verifier)

        with pytest.raises(InvalidMacaroon):
            caveat(predicate)

    def test_verify_project_no_projects_object(self, db_request):
        project = ProjectFactory.create(name="foobar")
        verifier = pretend.stub(context=project)
        caveat = V1Caveat(verifier)

        predicate = {
            "version": 1,
            "permissions": {"somethingthatisntprojects": ["blah"]},
        }
        with pytest.raises(InvalidMacaroon):
            caveat(predicate)

    @pytest.mark.parametrize(
        "predicate",
        [
            {"version": 1, "permissions": {"projects": ["foobar"]}},
            {"version": 2, "permissions": {"projects": [{"name": "foobar"}]}},
        ],
    )
    def test_verify_project(self, db_request, predicate):
        project = ProjectFactory.create(name="foobar")
        ReleaseFactory.create(project=project)
        verifier = pretend.stub(context=project)

        if predicate["version"] == 1:
            caveat = V1Caveat(verifier)
        else:
            caveat = V2Caveat(verifier)

        assert caveat(predicate) is True


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
        with pytest.raises(InvalidMacaroon):
            verifier.verify(key)
        assert verify.calls == [pretend.call(macaroon, key)]
