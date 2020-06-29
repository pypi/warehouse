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

from warehouse import tasks
from warehouse.accounts.interfaces import ITokenService, TokenExpired
from warehouse.packaging.models import RoleInvitation, RoleInvitationStatus


@tasks.task(ignore_result=True, acks_late=True)
def update_role_invitation_status(request):
    invites = (
        request.db.query(RoleInvitation)
        .filter(RoleInvitation.invite_status == RoleInvitationStatus.Pending.value)
        .all()
    )
    token_service = request.find_service(ITokenService, name="email")

    for invite in invites:
        try:
            token_service.loads(invite.token)
        except TokenExpired:
            invite.invite_status = RoleInvitationStatus.Expired.value
