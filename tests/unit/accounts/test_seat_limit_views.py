# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from pyramid.httpexceptions import HTTPSeeOther

from tests.common.db.accounts import EmailFactory, UserFactory
from tests.common.db.organizations import OrganizationInvitationFactory
from tests.unit.common.test_seat_limit_fixtures import (  # noqa: F401
    company_without_billing,
    mock_organization_services,
    organization_at_seat_limit,
    organization_with_available_seats,
)
from warehouse.accounts import views
from warehouse.organizations.models import OrganizationRole


@pytest.fixture
def mock_email_sending(monkeypatch):
    """Mock only email sending functions since we can't send emails in tests."""
    organization_member_added_email = pretend.call_recorder(
        lambda *args, **kwargs: None
    )
    added_as_organization_member_email = pretend.call_recorder(
        lambda *args, **kwargs: None
    )

    monkeypatch.setattr(
        views, "send_organization_member_added_email", organization_member_added_email
    )
    monkeypatch.setattr(
        views,
        "send_added_as_organization_member_email",
        added_as_organization_member_email,
    )

    return {
        "organization_member_added_email": organization_member_added_email,
        "added_as_organization_member_email": added_as_organization_member_email,
    }


@pytest.fixture
def mock_accounts_services(db_request):
    """Use REAL services where possible for accounts views."""

    def create_services(organization, new_user, owner, invitation):
        token_service = pretend.stub(
            loads=lambda token: {
                "action": "email-organization-role-verify",
                "desired_role": "Member",
                "user_id": new_user.id,
                "organization_id": organization.id,
                "submitter_id": owner.id,
            }
        )

        # Use REAL organization service for actual database operations!
        from warehouse.organizations.services import DatabaseOrganizationService

        organization_service = DatabaseOrganizationService(db_request.db)

        # Use REAL user service for actual database operations!
        from warehouse.accounts.services import DatabaseUserService

        user_service = DatabaseUserService(
            db_request.db,
            ratelimiters={},  # Empty ratelimiters for tests
            remote_addr="127.0.0.1",  # Test IP
            metrics=pretend.stub(),  # Stub metrics for tests
        )

        def find_service(iface, name=None, context=None):
            if name == "email":
                return token_service
            elif iface.__name__ == "IOrganizationService":
                return organization_service
            elif iface.__name__ == "IUserService":
                return user_service
            return None  # pragma: no cover

        return find_service, organization_service

    return create_services


class TestVerifyOrganizationRoleSeatLimit:
    """Test seat limit enforcement when accepting organization invitations."""

    def test_verify_role_blocked_at_seat_limit(
        self,
        db_request,
        organization_at_seat_limit,  # noqa: F811
        mock_email_sending,
        mock_accounts_services,
    ):
        """Test invitation blocked when organization is at seat limit."""
        organization, owner = organization_at_seat_limit

        # Create user trying to accept invitation
        new_user = UserFactory.create()
        EmailFactory.create(user=new_user, verified=True, primary=True)
        invitation = OrganizationInvitationFactory.create(
            organization=organization,
            user=new_user,
        )

        # Setup service mocks
        find_service, organization_service = mock_accounts_services(
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
        assert mock_email_sending["organization_member_added_email"].calls == []
        assert mock_email_sending["added_as_organization_member_email"].calls == []

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
        mock_email_sending,
        mock_accounts_services,
    ):
        """Test invitation succeeds when organization has available seats."""
        organization, owner = organization_with_available_seats

        # Create user accepting invitation
        new_user = UserFactory.create()
        EmailFactory.create(user=new_user, verified=True, primary=True)
        invitation = OrganizationInvitationFactory.create(
            organization=organization,
            user=new_user,
        )

        # Setup service mocks
        find_service, organization_service = mock_accounts_services(
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
        assert len(mock_email_sending["organization_member_added_email"].calls) == 1
        assert len(mock_email_sending["added_as_organization_member_email"].calls) == 1

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
        self, db_request, company_without_billing, mock_accounts_services  # noqa: F811
    ):
        """Test invitation fails when organization not in good standing."""
        organization, owner = company_without_billing

        # Create user trying to accept invitation
        new_user = UserFactory.create()
        EmailFactory.create(user=new_user, verified=True, primary=True)
        invitation = OrganizationInvitationFactory.create(
            organization=organization,
            user=new_user,
        )

        # Setup service mocks
        find_service, organization_service = mock_accounts_services(
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
