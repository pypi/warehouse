# SPDX-License-Identifier: Apache-2.0

import structlog

from warehouse import tasks
from warehouse.accounts.interfaces import ITokenService, TokenException, TokenExpired
from warehouse.packaging.models import RoleInvitation, RoleInvitationStatus

logger = structlog.get_logger(__name__)


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
        except TokenException:
            logger.warning(
                "Skipping role invitation with an unreadable token",
                invitation_id=str(invite.id),
            )
