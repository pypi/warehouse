# SPDX-License-Identifier: Apache-2.0

import pretend

from pyramid.httpexceptions import HTTPSeeOther
from webob.multidict import MultiDict

from tests.unit.common.test_seat_limit_fixtures import (  # noqa: F401
    company_without_billing,
    mock_email_sending_manage,
    mock_find_service_manage,
    mock_real_services,
    new_user_with_email,
    organization_at_seat_limit,
    organization_with_available_seats,
)
from warehouse.manage.views import organizations as org_views
from warehouse.manage.views.organizations import CreateOrganizationRoleForm
from warehouse.organizations.models import (
    OrganizationInvitation,
    OrganizationInvitationStatus,
)


class TestSeatLimitEnforcement:
    """Test seat limit enforcement in organization invitations."""

    def test_send_invitation_at_seat_limit(
        self,
        db_request,
        organization_at_seat_limit,  # noqa: F811
        new_user_with_email,  # noqa: F811
        mock_email_sending_manage,  # noqa: F811
        mock_find_service_manage,  # noqa: F811
        monkeypatch,
    ):
        """Test that invitations are blocked when at seat limit."""
        organization, owner = organization_at_seat_limit
        new_user = new_user_with_email
        mock_emails = mock_email_sending_manage

        # Setup service mocks
        find_service, organization_service = mock_find_service_manage()
        db_request.find_service = find_service

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
        assert mock_emails["send_organization_member_invited_email"].calls == []
        assert mock_emails["send_organization_role_verification_email"].calls == []

        # Verify redirect
        assert isinstance(result, HTTPSeeOther)

    def test_send_invitation_with_available_seats(
        self,
        db_request,
        organization_with_available_seats,  # noqa: F811
        new_user_with_email,  # noqa: F811
        mock_email_sending_manage,  # noqa: F811
        mock_find_service_manage,  # noqa: F811
        monkeypatch,
    ):
        """Test that invitations work when seats are available."""
        organization, owner = organization_with_available_seats
        new_user = new_user_with_email
        mock_emails = mock_email_sending_manage

        # Setup service mocks
        find_service, organization_service = mock_find_service_manage()
        db_request.find_service = find_service

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

        # Mock organization_owners helper
        monkeypatch.setattr(
            org_views, "organization_owners", lambda request, org: [owner]
        )

        # Mock record_event to avoid Redis/event system dependencies
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
        assert len(mock_emails["send_organization_member_invited_email"].calls) == 1
        assert len(mock_emails["send_organization_role_verification_email"].calls) == 1

        # Verify an invitation was actually created in the database
        invitation = (
            db_request.db.query(OrganizationInvitation)
            .filter_by(organization_id=organization.id, user_id=new_user.id)
            .first()
        )
        assert invitation is not None
        assert invitation.invite_status == OrganizationInvitationStatus.Pending

        # Verify redirect
        assert isinstance(result, HTTPSeeOther)

    def test_send_invitation_organization_not_in_good_standing(
        self,
        db_request,
        company_without_billing,  # noqa: F811
        new_user_with_email,  # noqa: F811
        mock_email_sending_manage,  # noqa: F811
        mock_find_service_manage,  # noqa: F811
        monkeypatch,
    ):
        """Test that invitations are blocked when organization not in good standing."""
        organization, owner = company_without_billing
        new_user = new_user_with_email
        mock_emails = mock_email_sending_manage

        # Setup service mocks
        find_service, organization_service = mock_find_service_manage()
        db_request.find_service = find_service

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
        assert mock_emails["send_organization_member_invited_email"].calls == []
        assert mock_emails["send_organization_role_verification_email"].calls == []

        # Verify redirect
        assert isinstance(result, HTTPSeeOther)
