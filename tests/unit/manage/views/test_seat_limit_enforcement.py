# SPDX-License-Identifier: Apache-2.0

import datetime

import pretend

from pyramid.httpexceptions import HTTPSeeOther
from webob.multidict import MultiDict

from tests.common.db.accounts import EmailFactory, UserFactory
from tests.common.db.organizations import (
    OrganizationFactory,
    OrganizationManualActivationFactory,
    OrganizationRoleFactory,
)
from warehouse.accounts.interfaces import IUserService
from warehouse.manage.views import organizations as org_views
from warehouse.manage.views.organizations import CreateOrganizationRoleForm
from warehouse.organizations.models import OrganizationRoleType
from warehouse.organizations.services import IOrganizationService


class TestSeatLimitEnforcement:
    """Test seat limit enforcement in organization invitations."""

    def test_send_invitation_at_seat_limit(self, db_request, monkeypatch):
        """Test that invitations are blocked when at seat limit."""
        # Create organization with manual activation at limit
        organization = OrganizationFactory.create()
        # Create activation that expires far in the future
        future_date = datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)
        OrganizationManualActivationFactory.create(
            organization=organization,
            seat_limit=2,  # Only 2 seats
            expires=future_date,
        )

        # Create 2 existing members to reach the limit
        owner = UserFactory.create()
        member = UserFactory.create()
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=member,
            role_name=OrganizationRoleType.Member,
        )

        # User to invite
        new_user = UserFactory.create()
        EmailFactory.create(user=new_user, verified=True, primary=True)

        # Setup request
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {"username": new_user.username, "role_name": "Member"}
        )
        db_request.user = owner
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/")

        # Mock services
        user_service = pretend.stub(
            find_userid=lambda username: new_user.id,
            get_user=lambda userid: new_user,
        )
        organization_service = pretend.stub(
            get_organization_role_by_user=lambda org_id, user_id: None,
            get_organization_invite_by_user=lambda org_id, user_id: None,
            get_organization_roles=lambda org_id: [],
            get_organization_invites=lambda org_id: [],
        )
        token_service = pretend.stub(
            dumps=lambda data: "fake-token",
            max_age=300,  # 5 minutes
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
        send_organization_member_invited_email = pretend.call_recorder(
            lambda r, u, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_member_invited_email",
            send_organization_member_invited_email,
        )
        send_organization_role_verification_email = pretend.call_recorder(
            lambda r, u, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_role_verification_email",
            send_organization_role_verification_email,
        )

        # Mock organization_owners helper
        monkeypatch.setattr(
            org_views, "organization_owners", lambda request, org: [owner]
        )

        # Call the actual manage_organization_roles view
        result = org_views.manage_organization_roles(
            organization, db_request, _form_class=CreateOrganizationRoleForm
        )

        # Verify seat limit error was flashed
        assert len(db_request.session.flash.calls) == 1
        flash_call = db_request.session.flash.calls[0]
        assert "seat limit" in flash_call.args[0]
        assert flash_call.kwargs["queue"] == "error"

        # Verify no emails were sent
        assert send_organization_member_invited_email.calls == []
        assert send_organization_role_verification_email.calls == []

        # Verify redirect
        assert isinstance(result, HTTPSeeOther)

    def test_send_invitation_with_available_seats(self, db_request, monkeypatch):
        """Test that invitations work when seats are available."""
        # Create organization with manual activation with available seats
        organization = OrganizationFactory.create()
        # Create activation that expires far in the future
        future_date = datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)
        OrganizationManualActivationFactory.create(
            organization=organization,
            seat_limit=10,  # Plenty of seats
            expires=future_date,
        )

        # Create 1 existing member
        owner = UserFactory.create()
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner,
            role_name=OrganizationRoleType.Owner,
        )

        # User to invite
        new_user = UserFactory.create()
        EmailFactory.create(user=new_user, verified=True, primary=True)

        # Setup request
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {"username": new_user.username, "role_name": "Member"}
        )
        db_request.user = owner
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/")

        # Mock services
        user_service = pretend.stub(
            find_userid=lambda username: new_user.id,
            get_user=lambda userid: new_user,
        )
        organization_service = pretend.stub(
            get_organization_role_by_user=pretend.call_recorder(
                lambda org_id, user_id: None
            ),
            get_organization_invite_by_user=pretend.call_recorder(
                lambda org_id, user_id: None
            ),
            add_organization_invite=pretend.call_recorder(lambda **kw: None),
            get_organization_roles=lambda org_id: [],
            get_organization_invites=lambda org_id: [],
        )
        token_service = pretend.stub(
            dumps=pretend.call_recorder(lambda data: "fake-token"),
            max_age=300,  # 5 minutes
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
        send_organization_member_invited_email = pretend.call_recorder(
            lambda r, u, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_member_invited_email",
            send_organization_member_invited_email,
        )
        send_organization_role_verification_email = pretend.call_recorder(
            lambda r, u, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_role_verification_email",
            send_organization_role_verification_email,
        )

        # Mock organization_owners helper
        monkeypatch.setattr(
            org_views, "organization_owners", lambda request, org: [owner]
        )

        # Mock record_event to avoid any Redis issues
        organization.record_event = pretend.call_recorder(lambda **kw: None)
        new_user.record_event = pretend.call_recorder(lambda **kw: None)

        # Call the actual manage_organization_roles view
        result = org_views.manage_organization_roles(
            organization, db_request, _form_class=CreateOrganizationRoleForm
        )

        # Verify success message was flashed
        assert len(db_request.session.flash.calls) == 1
        flash_call = db_request.session.flash.calls[0]
        assert f"Invitation sent to '{new_user.username}'" in flash_call.args[0]
        assert flash_call.kwargs["queue"] == "success"

        # Verify emails were sent
        assert len(send_organization_member_invited_email.calls) == 1
        assert len(send_organization_role_verification_email.calls) == 1

        # Verify organization service was called to add invite
        assert len(organization_service.add_organization_invite.calls) == 1

        # Verify redirect
        assert isinstance(result, HTTPSeeOther)

    def test_send_invitation_organization_not_in_good_standing(
        self, db_request, monkeypatch
    ):
        """Test that invitations are blocked when organization not in good standing."""
        # Create Company organization without billing (not in good standing)
        organization = OrganizationFactory.create(orgtype="Company")

        # Create 1 existing member
        owner = UserFactory.create()
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner,
            role_name=OrganizationRoleType.Owner,
        )

        # User to invite
        new_user = UserFactory.create()
        EmailFactory.create(user=new_user, verified=True, primary=True)

        # Setup request
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {"username": new_user.username, "role_name": "Member"}
        )
        db_request.user = owner
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/")

        # Mock services
        user_service = pretend.stub(
            find_userid=lambda username: new_user.id,
            get_user=lambda userid: new_user,
        )
        organization_service = pretend.stub(
            get_organization_role_by_user=lambda org_id, user_id: None,
            get_organization_invite_by_user=lambda org_id, user_id: None,
            get_organization_roles=lambda org_id: [],
            get_organization_invites=lambda org_id: [],
        )
        token_service = pretend.stub(
            dumps=lambda data: "fake-token",
            max_age=300,  # 5 minutes
        )

        def find_service(iface, **kw):
            if iface == IUserService:
                return user_service
            elif iface == IOrganizationService:
                return organization_service
            else:
                return {"email": token_service}.get(kw.get("name"))

        db_request.find_service = find_service

        # Mock email functions (they won't be called due to not being in good standing)
        send_organization_member_invited_email = pretend.call_recorder(
            lambda r, u, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_member_invited_email",
            send_organization_member_invited_email,
        )
        send_organization_role_verification_email = pretend.call_recorder(
            lambda r, u, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_role_verification_email",
            send_organization_role_verification_email,
        )

        # Mock organization_owners helper
        monkeypatch.setattr(
            org_views, "organization_owners", lambda request, org: [owner]
        )

        # Call the actual manage_organization_roles view
        result = org_views.manage_organization_roles(
            organization, db_request, _form_class=CreateOrganizationRoleForm
        )

        # Verify error was flashed
        assert len(db_request.session.flash.calls) == 1
        flash_call = db_request.session.flash.calls[0]
        assert (
            "Cannot invite new member. Organization is not in good standing."
            in flash_call.args[0]
        )
        assert flash_call.kwargs["queue"] == "error"

        # Verify no emails were sent
        assert send_organization_member_invited_email.calls == []
        assert send_organization_role_verification_email.calls == []

        # Verify redirect
        assert isinstance(result, HTTPSeeOther)
