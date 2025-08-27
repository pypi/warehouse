# SPDX-License-Identifier: Apache-2.0

import datetime

import pretend
import pytest

from tests.common.db.accounts import EmailFactory, UserFactory
from tests.common.db.organizations import (
    OrganizationFactory,
    OrganizationManualActivationFactory,
    OrganizationRoleFactory,
)
from warehouse.accounts.services import DatabaseUserService
from warehouse.organizations.models import OrganizationRoleType
from warehouse.organizations.services import DatabaseOrganizationService


@pytest.fixture
def organization_at_seat_limit(db_session):
    """Create organization with manual activation that's at its seat limit."""
    organization = OrganizationFactory.create()
    future_date = datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)
    OrganizationManualActivationFactory.create(
        organization=organization,
        seat_limit=2,  # Only 2 seats available
        expires=future_date,
    )

    # Create exactly 2 members to reach the limit
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

    return organization, owner


@pytest.fixture
def organization_with_available_seats(db_session):
    """Create organization with manual activation that has available seats."""
    organization = OrganizationFactory.create()
    future_date = datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)
    OrganizationManualActivationFactory.create(
        organization=organization,
        seat_limit=10,  # Plenty of seats
        expires=future_date,
    )

    # Create only 1 member, leaving 9 seats available
    owner = UserFactory.create()
    OrganizationRoleFactory.create(
        organization=organization,
        user=owner,
        role_name=OrganizationRoleType.Owner,
    )

    return organization, owner


@pytest.fixture
def company_without_billing(db_session):
    """Create Company organization without any billing (not in good standing)."""
    organization = OrganizationFactory.create(orgtype="Company")
    owner = UserFactory.create()
    OrganizationRoleFactory.create(
        organization=organization,
        user=owner,
        role_name=OrganizationRoleType.Owner,
    )

    return organization, owner


@pytest.fixture
def new_user_with_email(db_session):
    """Create a new user with verified primary email."""
    user = UserFactory.create()
    EmailFactory.create(user=user, verified=True, primary=True)
    return user


@pytest.fixture
def mock_real_services(db_request):
    """Use REAL database services for all operations."""

    def get_services():
        # Use REAL organization service for actual database operations!
        organization_service = DatabaseOrganizationService(db_request.db)

        # Use REAL user service for actual database operations!
        user_service = DatabaseUserService(
            db_request.db,
            ratelimiters={},  # Empty ratelimiters for tests
            remote_addr="127.0.0.1",  # Test IP
            metrics=pretend.stub(),  # Stub metrics for tests
        )

        return organization_service, user_service

    return get_services


@pytest.fixture
def mock_email_sending_accounts(monkeypatch):
    """Mock email sending for accounts views."""
    from warehouse.accounts import views

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
def mock_email_sending_manage(monkeypatch):
    """Mock email sending for manage views."""
    from warehouse.manage.views import organizations as org_views

    send_organization_member_invited_email = pretend.call_recorder(
        lambda *args, **kwargs: None
    )
    send_organization_role_verification_email = pretend.call_recorder(
        lambda *args, **kwargs: None
    )

    monkeypatch.setattr(
        org_views,
        "send_organization_member_invited_email",
        send_organization_member_invited_email,
    )
    monkeypatch.setattr(
        org_views,
        "send_organization_role_verification_email",
        send_organization_role_verification_email,
    )

    return {
        "send_organization_member_invited_email": (
            send_organization_member_invited_email
        ),
        "send_organization_role_verification_email": (
            send_organization_role_verification_email
        ),
    }


@pytest.fixture
def mock_find_service_accounts(mock_real_services):
    """Create find_service function for accounts views that accept invitations."""

    def create_find_service(organization, new_user, owner, invitation):
        org_service, user_service = mock_real_services()

        token_service = pretend.stub(
            loads=lambda token: {
                "action": "email-organization-role-verify",
                "desired_role": "Member",
                "user_id": new_user.id,
                "organization_id": organization.id,
                "submitter_id": owner.id,
            }
        )

        def find_service(iface, name=None, context=None):
            if name == "email":
                return token_service
            elif iface.__name__ == "IOrganizationService":
                return org_service
            elif iface.__name__ == "IUserService":
                return user_service
            return None  # pragma: no cover

        return find_service, org_service

    return create_find_service


@pytest.fixture
def mock_find_service_manage(mock_real_services):
    """Create find_service function for manage views that send invitations."""

    def create_find_service():
        org_service, user_service = mock_real_services()

        # Token service for generating invitation tokens - must be mocked
        token_service = pretend.stub(
            dumps=pretend.call_recorder(lambda data: "fake-token"),
            max_age=300,  # 5 minutes
        )

        def find_service(iface, name=None, context=None, **kw):
            if iface.__name__ == "IUserService":
                return user_service
            elif iface.__name__ == "IOrganizationService":
                return org_service
            elif name == "email":
                return token_service
            return None  # pragma: no cover

        return find_service, org_service

    return create_find_service
