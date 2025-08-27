# SPDX-License-Identifier: Apache-2.0

import pretend

from pyramid.httpexceptions import HTTPSeeOther

from tests.common.db.organizations import OrganizationInvitationFactory
from tests.unit.common.test_seat_limit_fixtures import (  # noqa: F401
    company_without_billing,
    mock_email_sending_accounts,
    mock_find_service_accounts,
    mock_real_services,
    new_user_with_email,
    organization_at_seat_limit,
    organization_with_available_seats,
)
from warehouse.accounts import views
from warehouse.organizations.models import OrganizationRole


class TestVerifyOrganizationRoleSeatLimit:
    """Test seat limit enforcement when accepting organization invitations."""

    def test_verify_role_blocked_at_seat_limit(
        self,
        db_request,
        organization_at_seat_limit,  # noqa: F811
        new_user_with_email,  # noqa: F811
        mock_email_sending_accounts,  # noqa: F811
        mock_find_service_accounts,  # noqa: F811
    ):
        """Test invitation blocked when organization is at seat limit."""
        organization, owner = organization_at_seat_limit
        new_user = new_user_with_email
        mock_emails = mock_email_sending_accounts

        invitation = OrganizationInvitationFactory.create(
            organization=organization,
            user=new_user,
        )

        # Setup service mocks
        find_service, organization_service = mock_find_service_accounts(
            organization, new_user, owner, invitation
        )
        db_request.find_service = find_service

        # Setup request with real data
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

        # Call the actual view function
        result = views.verify_organization_role(db_request)

        # Verify seat limit error was shown
        assert len(db_request.session.flash.calls) == 1
        flash_call = db_request.session.flash.calls[0]
        assert "seat limit" in flash_call.args[0]
        assert flash_call.kwargs["queue"] == "error"

        # Verify no emails were sent (blocked by seat limit)
        assert mock_emails["organization_member_added_email"].calls == []
        assert mock_emails["added_as_organization_member_email"].calls == []

        # Verify redirect
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage.organizations"

        # Verify no new organization role was created
        roles_count = len(organization.roles)
        assert roles_count == 2  # Still just owner + member

    def test_verify_role_succeeds_with_available_seats(
        self,
        db_request,
        organization_with_available_seats,  # noqa: F811
        new_user_with_email,  # noqa: F811
        mock_email_sending_accounts,  # noqa: F811
        mock_find_service_accounts,  # noqa: F811
    ):
        """Test invitation succeeds when organization has available seats."""
        organization, owner = organization_with_available_seats
        new_user = new_user_with_email
        mock_emails = mock_email_sending_accounts

        invitation = OrganizationInvitationFactory.create(
            organization=organization,
            user=new_user,
        )

        # Setup service mocks
        find_service, organization_service = mock_find_service_accounts(
            organization, new_user, owner, invitation
        )
        db_request.find_service = find_service

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

        # Mock record_event to avoid Redis/event system dependencies
        organization.record_event = pretend.call_recorder(lambda **kw: None)
        new_user.record_event = pretend.call_recorder(lambda **kw: None)
        owner.record_event = pretend.call_recorder(lambda **kw: None)

        # Call the actual view function
        result = views.verify_organization_role(db_request)

        # Verify success message was shown
        assert len(db_request.session.flash.calls) == 1
        flash_call = db_request.session.flash.calls[0]
        assert "You are now" in flash_call.args[0]
        assert flash_call.kwargs["queue"] == "success"

        # Verify emails were sent
        assert len(mock_emails["organization_member_added_email"].calls) == 1
        assert len(mock_emails["added_as_organization_member_email"].calls) == 1

        # Verify redirect to manage organization roles
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage.organization.roles"

        # Verify the user was actually added to the organization
        # Check database state directly
        new_role = (
            db_request.db.query(OrganizationRole)
            .filter_by(organization_id=organization.id, user_id=new_user.id)
            .first()
        )
        assert new_role is not None
        assert new_role.role_name == "Member"

    def test_verify_role_blocked_when_not_in_good_standing(
        self,
        db_request,
        company_without_billing,  # noqa: F811
        new_user_with_email,  # noqa: F811
        mock_find_service_accounts,  # noqa: F811
    ):
        """Test invitation fails when organization not in good standing."""
        organization, owner = company_without_billing
        new_user = new_user_with_email

        invitation = OrganizationInvitationFactory.create(
            organization=organization,
            user=new_user,
        )

        # Setup service mocks
        find_service, organization_service = mock_find_service_accounts(
            organization, new_user, owner, invitation
        )
        db_request.find_service = find_service

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

        # Call the actual view function
        result = views.verify_organization_role(db_request)

        # Verify good standing error was shown
        assert len(db_request.session.flash.calls) == 1
        flash_call = db_request.session.flash.calls[0]
        assert "not in good standing" in flash_call.args[0]
        assert flash_call.kwargs["queue"] == "error"

        # Verify redirect
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage.organizations"
