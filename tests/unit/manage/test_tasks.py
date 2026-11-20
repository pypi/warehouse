# SPDX-License-Identifier: Apache-2.0

import pytest

from freezegun import freeze_time

from warehouse.accounts.interfaces import ITokenService
from warehouse.accounts.services import TokenService
from warehouse.manage.tasks import update_role_invitation_status
from warehouse.packaging.models import RoleInvitationStatus

from ...common.db.packaging import RoleInvitationFactory


class TestUpdateInvitationStatus:
    @pytest.fixture
    def email_token_service(self, pyramid_services):
        """
        Registered under "email" only, so a lookup by any other name misses it.
        """
        service = TokenService(secret="secret", salt="email", max_age=21600)
        pyramid_services.register_service(service, ITokenService, None, name="email")
        return service

    def test_update_invitation_status(self, db_request, email_token_service):
        with freeze_time("2020-01-01"):
            token = email_token_service.dumps({})
        invite = RoleInvitationFactory.create(token=token)

        update_role_invitation_status(db_request)

        assert invite.invite_status == RoleInvitationStatus.Expired

    def test_unreadable_tokens_skipped(self, db_request, email_token_service):
        """
        Tokens that fail verification are left pending, and do not stop the
        invitations after them from being processed.
        """
        other = TokenService(secret="other", salt="email", max_age=21600)
        invalid = RoleInvitationFactory.create(token=other.dumps({}))
        missing = RoleInvitationFactory.create(token="")
        with freeze_time("2020-01-01"):
            expired = RoleInvitationFactory.create(token=email_token_service.dumps({}))

        update_role_invitation_status(db_request)

        assert invalid.invite_status == RoleInvitationStatus.Pending
        assert missing.invite_status == RoleInvitationStatus.Pending
        assert expired.invite_status == RoleInvitationStatus.Expired

    def test_no_updates(self, db_request, email_token_service):
        invite = RoleInvitationFactory.create(token=email_token_service.dumps({}))

        update_role_invitation_status(db_request)

        assert invite.invite_status == RoleInvitationStatus.Pending
