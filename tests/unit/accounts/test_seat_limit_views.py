# SPDX-License-Identifier: Apache-2.0

import datetime

import pretend

from pyramid.httpexceptions import HTTPSeeOther

from tests.common.db.accounts import EmailFactory, UserFactory
from tests.common.db.organizations import (
    OrganizationFactory,
    OrganizationInvitationFactory,
    OrganizationManualActivationFactory,
    OrganizationRoleFactory,
)
from warehouse.accounts import views
from warehouse.accounts.interfaces import IUserService
from warehouse.organizations.models import OrganizationRoleType
from warehouse.organizations.services import IOrganizationService


class TestVerifyOrganizationRoleSeatLimit:
    """Test seat limit enforcement when accepting organization invitations."""

    def test_verify_role_at_seat_limit(self, db_request, monkeypatch):
        """Test that accepting invitation is blocked when at seat limit."""
        # Create organization with manual activation at limit
        organization = OrganizationFactory.create()
        # Create activation that expires far in the future
        future_date = datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)
        manual_activation = OrganizationManualActivationFactory.create(
            organization=organization,
            seat_limit=2,  # Only 2 seats
            expires=future_date,
        )
        organization.manual_activation = manual_activation

        # Create 2 existing members to reach the limit
        owner = UserFactory.create()
        member = UserFactory.create()
        owner_role = OrganizationRoleFactory.create(
            organization=organization,
            user=owner,
            role_name=OrganizationRoleType.Owner,
        )
        member_role = OrganizationRoleFactory.create(
            organization=organization,
            user=member,
            role_name=OrganizationRoleType.Member,
        )
        # Ensure the organization.roles relationship is properly loaded
        organization.roles = [owner_role, member_role]

        # User trying to accept invitation
        new_user = UserFactory.create()
        EmailFactory.create(user=new_user, verified=True, primary=True)
        invitation = OrganizationInvitationFactory.create(
            organization=organization,
            user=new_user,
        )

        # Setup request
        db_request.user = new_user
        db_request.method = "POST"
        db_request.GET.update({"token": "fake-token"})
        db_request.POST = {"accept": "Accept"}
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda name, **kw: f"/{name}")
        db_request.remote_addr = "192.168.1.1"
        db_request._ = lambda text, **kw: text.format(**kw.get("mapping", {}))

        # Mock services
        token_service = pretend.stub(
            loads=pretend.call_recorder(
                lambda token: {
                    "action": "email-organization-role-verify",
                    "desired_role": "Member",
                    "user_id": new_user.id,
                    "organization_id": organization.id,
                    "submitter_id": owner.id,
                }
            )
        )
        user_service = pretend.stub(
            get_user=lambda userid: owner if userid == owner.id else new_user,
        )
        # Make sure the organization returned by service has manual activation

        def get_organization_with_manual_activation(org_id):

            # Ensure manual activation and roles are properly attached
            organization.manual_activation = manual_activation
            organization.roles = [owner_role, member_role]
            return organization

        organization_service = pretend.stub(
            get_organization=get_organization_with_manual_activation,
            get_organization_invite_by_user=lambda org_id, user_id: invitation,
            get_organization_role_by_user=lambda org_id, user_id: None,
            add_organization_role=pretend.call_recorder(lambda **kw: None),
            delete_organization_invite=pretend.call_recorder(lambda invite_id: None),
        )

        def find_service(iface, **kw):
            if iface == IUserService:
                return user_service
            elif iface == IOrganizationService:
                return organization_service
            else:
                return {"email": token_service}.get(kw.get("name"))

        db_request.find_service = find_service

        # Mock email functions (they won't be called due to seat limit)
        organization_member_added_email = pretend.call_recorder(
            lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_member_added_email",
            organization_member_added_email,
        )
        added_as_organization_member_email = pretend.call_recorder(
            lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            views,
            "send_added_as_organization_member_email",
            added_as_organization_member_email,
        )

        # Call verify_organization_role
        result = views.verify_organization_role(db_request)

        # Verify seat limit error was flashed
        assert len(db_request.session.flash.calls) == 1
        flash_call = db_request.session.flash.calls[0]
        assert "Cannot accept invitation" in flash_call.args[0]
        assert "seat limit" in flash_call.args[0]
        assert flash_call.kwargs["queue"] == "error"

        # Verify no emails were sent
        assert organization_member_added_email.calls == []
        assert added_as_organization_member_email.calls == []

        # Verify redirect to manage organizations
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage.organizations"

    def test_verify_role_with_available_seats(self, db_request, monkeypatch):
        """Test that accepting invitation works when seats are available."""
        # Create organization with manual activation with available seats
        organization = OrganizationFactory.create()
        # Create activation that expires far in the future
        future_date = datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)
        manual_activation = OrganizationManualActivationFactory.create(
            organization=organization,
            seat_limit=10,  # Plenty of seats
            expires=future_date,
        )
        organization.manual_activation = manual_activation

        # Create 1 existing member
        owner = UserFactory.create()
        owner_role = OrganizationRoleFactory.create(
            organization=organization,
            user=owner,
            role_name=OrganizationRoleType.Owner,
        )
        # Ensure the organization.roles relationship is properly loaded
        organization.roles = [owner_role]

        # User accepting invitation
        new_user = UserFactory.create()
        EmailFactory.create(user=new_user, verified=True, primary=True)
        invitation = OrganizationInvitationFactory.create(
            organization=organization,
            user=new_user,
        )

        # Setup request
        db_request.user = new_user
        db_request.method = "POST"
        db_request.GET.update({"token": "fake-token"})
        db_request.POST = {"accept": "Accept"}
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda name, **kw: f"/{name}")
        db_request.remote_addr = "192.168.1.1"
        db_request._ = lambda text, **kw: text.format(**kw.get("mapping", {}))

        # Mock services
        token_service = pretend.stub(
            loads=pretend.call_recorder(
                lambda token: {
                    "action": "email-organization-role-verify",
                    "desired_role": "Member",
                    "user_id": new_user.id,
                    "organization_id": organization.id,
                    "submitter_id": owner.id,
                }
            )
        )
        user_service = pretend.stub(
            get_user=lambda userid: owner if userid == owner.id else new_user,
        )
        # Make sure the organization returned by service has manual activation

        def get_organization_with_manual_activation(org_id):

            # Ensure manual activation and roles are properly attached
            organization.manual_activation = manual_activation
            organization.roles = [owner_role]
            return organization

        organization_service = pretend.stub(
            get_organization=get_organization_with_manual_activation,
            get_organization_invite_by_user=lambda org_id, user_id: invitation,
            get_organization_role_by_user=lambda org_id, user_id: None,
            add_organization_role=pretend.call_recorder(lambda **kw: None),
            delete_organization_invite=pretend.call_recorder(lambda invite_id: None),
        )

        def find_service(iface, **kw):
            if iface == IUserService:
                return user_service
            elif iface == IOrganizationService:
                return organization_service
            else:
                return {"email": token_service}.get(kw.get("name"))

        db_request.find_service = find_service

        # Mock email functions
        organization_member_added_email = pretend.call_recorder(
            lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_member_added_email",
            organization_member_added_email,
        )
        added_as_organization_member_email = pretend.call_recorder(
            lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            views,
            "send_added_as_organization_member_email",
            added_as_organization_member_email,
        )

        # Mock record_event to avoid any issues
        organization.record_event = pretend.call_recorder(lambda **kw: None)
        new_user.record_event = pretend.call_recorder(lambda **kw: None)
        owner.record_event = pretend.call_recorder(lambda **kw: None)

        # Call verify_organization_role
        result = views.verify_organization_role(db_request)

        # Verify success message was flashed
        assert len(db_request.session.flash.calls) == 1
        flash_call = db_request.session.flash.calls[0]
        assert "You are now" in flash_call.args[0]
        assert flash_call.kwargs["queue"] == "success"

        # Verify emails were sent
        assert len(organization_member_added_email.calls) == 1
        assert len(added_as_organization_member_email.calls) == 1

        # Verify organization service was called to add role
        assert len(organization_service.add_organization_role.calls) == 1
        assert len(organization_service.delete_organization_invite.calls) == 1

        # Verify redirect to manage organization roles
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage.organization.roles"
