# SPDX-License-Identifier: Apache-2.0

import uuid

import pytest

from pyramid.httpexceptions import HTTPNotFound, HTTPSeeOther

from warehouse.admin.views import gating
from warehouse.gating.models import GateStatus

from ....common.db.accounts import UserFactory
from ....common.db.gating import ReleaseGateFactory
from ....common.db.packaging import FileFactory, ProjectFactory, ReleaseFactory


class TestGatingList:
    def test_no_withheld_releases(self, db_request):
        assert gating.gating_list(db_request) == {"gates": []}

    def test_lists_pending_and_failed_oldest_first(self, db_request):
        project = ProjectFactory.create()
        pending_release = ReleaseFactory.create(project=project, gated=True)
        failed_release = ReleaseFactory.create(project=project, gated=True)

        failed = ReleaseGateFactory.create(
            release=failed_release,
            kind="held",
            status=GateStatus.Failed,
        )
        pending = ReleaseGateFactory.create(
            release=pending_release,
            kind="waiting",
            status=GateStatus.Pending,
        )
        db_request.db.flush()

        gates = gating.gating_list(db_request)["gates"]

        assert set(gates) == {failed, pending}

    def test_excludes_resolved_gates(self, db_request):
        release = ReleaseFactory.create(gated=False)
        for status in (GateStatus.Passed, GateStatus.Bypassed, GateStatus.Expired):
            ReleaseGateFactory.create(
                release=ReleaseFactory.create(project=release.project),
                kind="held",
                status=status,
            )

        assert gating.gating_list(db_request)["gates"] == []


class TestGatingBypass:
    def test_bypass_publishes_the_release(self, db_request, gate_service, mocker):
        release = ReleaseFactory.create(gated=True)
        FileFactory.create(release=release, cached=False)
        gate = ReleaseGateFactory.create(
            release=release, kind="held", status=GateStatus.Failed
        )
        db_request.db.flush()

        user = UserFactory.create()
        db_request.user = user
        db_request.matchdict = {
            "release_id": str(release.id),
            "kind": "held",
        }
        db_request.POST = {"note": "false positive, reviewed by hand"}
        mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="/admin/gating/"
        )
        mocker.spy(db_request.session, "flash")

        result = gating.gating_bypass(db_request)

        assert isinstance(result, HTTPSeeOther)
        # Bypassed, not Passed: a person overrode the policy.
        assert gate.status == GateStatus.Bypassed
        assert gate.resolved_by == user.username
        assert gate.note == "false positive, reviewed by hand"
        assert release.gated is False
        db_request.session.flash.assert_called_once()

    def test_bypass_without_a_note_records_a_default(
        self, db_request, gate_service, mocker
    ):
        release = ReleaseFactory.create(gated=True)
        gate = ReleaseGateFactory.create(
            release=release, kind="held", status=GateStatus.Failed
        )
        db_request.db.flush()

        db_request.user = UserFactory.create()
        db_request.matchdict = {
            "release_id": str(release.id),
            "kind": "held",
        }
        db_request.POST = {}
        mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="/admin/gating/"
        )
        mocker.spy(db_request.session, "flash")

        gating.gating_bypass(db_request)

        assert gate.note == "Bypassed by an administrator"

    def test_unrecognized_gate_kind_is_not_found(
        self, db_request, gate_service, mocker
    ):
        """There is no fixed set of kinds, so an unrecognized one matches no row."""
        release = ReleaseFactory.create(gated=True)
        ReleaseGateFactory.create(
            release=release, kind="held", status=GateStatus.Failed
        )
        db_request.db.flush()

        db_request.user = UserFactory.create()
        db_request.matchdict = {
            "release_id": str(release.id),
            "kind": "not-a-real-kind",
        }
        db_request.POST = {}

        with pytest.raises(HTTPNotFound):
            gating.gating_bypass(db_request)

    def test_bypasses_a_gate_whose_policy_is_no_longer_registered(
        self, db_request, gate_service, mocker
    ):
        """A retired gate is exactly when a release would otherwise be stuck."""
        release = ReleaseFactory.create(gated=True)
        gate = ReleaseGateFactory.create(
            release=release, kind="retired", status=GateStatus.Failed
        )
        db_request.db.flush()

        db_request.user = UserFactory.create()
        db_request.matchdict = {
            "release_id": str(release.id),
            "kind": "retired",
        }
        db_request.POST = {}
        mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="/admin/gating/"
        )
        mocker.spy(db_request.session, "flash")

        result = gating.gating_bypass(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert gate.status == GateStatus.Bypassed
        assert release.gated is False

    def test_unknown_release_is_not_found(self, db_request):
        db_request.matchdict = {
            "release_id": str(uuid.uuid4()),
            "kind": "held",
        }

        with pytest.raises(HTTPNotFound):
            gating.gating_bypass(db_request)

    def test_release_without_that_gate_is_not_found(
        self, db_request, gate_service, mocker
    ):
        release = ReleaseFactory.create(gated=False)
        db_request.user = UserFactory.create()
        db_request.matchdict = {
            "release_id": str(release.id),
            "kind": "held",
        }
        db_request.POST = {}

        with pytest.raises(HTTPNotFound):
            gating.gating_bypass(db_request)
