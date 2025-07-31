# SPDX-License-Identifier: Apache-2.0

from warehouse import tasks
from warehouse.accounts.interfaces import ITokenService, TokenExpired
from warehouse.packaging.models import RoleInvitation, RoleInvitationStatus


@tasks.task(ignore_result=True, acks_late=True)
def update_role_invitation_status(request):
    invites = (
        request.db.query(RoleInvitation)
        .filter(RoleInvitation.invite_status == RoleInvitationStatus.Pending)
        .all()
    )
    token_service = request.find_service(ITokenService, name="email")

    for invite in invites:
        try:
            token_service.loads(invite.token)
        except TokenExpired:
            invite.invite_status = RoleInvitationStatus.Expired
