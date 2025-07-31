# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse.accounts.interfaces import ITokenService, TokenExpired
from warehouse.manage.tasks import update_role_invitation_status
from warehouse.packaging.models import RoleInvitationStatus

from ...common.db.packaging import ProjectFactory, RoleInvitationFactory, UserFactory


class TestUpdateInvitationStatus:
    def test_update_invitation_status(self, db_request):
        project = ProjectFactory.create()
        user = UserFactory.create()
        invite = RoleInvitationFactory(user=user, project=project)

        token_service = pretend.stub(loads=pretend.raiser(TokenExpired))
        db_request.find_service = pretend.call_recorder(lambda *a, **kw: token_service)

        update_role_invitation_status(db_request)

        assert db_request.find_service.calls == [
            pretend.call(ITokenService, name="email")
        ]
        assert invite.invite_status == RoleInvitationStatus.Expired

    def test_no_updates(self, db_request):
        project = ProjectFactory.create()
        user = UserFactory.create()
        invite = RoleInvitationFactory(user=user, project=project)

        token_service = pretend.stub(loads=lambda token: {})
        db_request.find_service = pretend.call_recorder(lambda *a, **kw: token_service)

        update_role_invitation_status(db_request)

        assert db_request.find_service.calls == [
            pretend.call(ITokenService, name="email")
        ]
        assert invite.invite_status == RoleInvitationStatus.Pending
