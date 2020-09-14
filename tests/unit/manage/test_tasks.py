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
