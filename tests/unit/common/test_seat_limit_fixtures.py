# SPDX-License-Identifier: Apache-2.0

import datetime

import pretend
import pytest

from tests.common.db.accounts import UserFactory
from tests.common.db.organizations import (
    OrganizationFactory,
    OrganizationManualActivationFactory,
    OrganizationRoleFactory,
)
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
def mock_organization_services(db_request):
    """Use REAL services where possible - only mock what can't be real in tests."""

    def create_services(owner, new_user):
        # Use REAL organization service for actual database operations!
        organization_service = DatabaseOrganizationService(db_request.db)

        # Use REAL user service for actual database operations!
        from warehouse.accounts.services import DatabaseUserService

        user_service = DatabaseUserService(
            db_request.db,
            ratelimiters={},  # Empty ratelimiters for tests
            remote_addr="127.0.0.1",  # Test IP
            metrics=pretend.stub(),  # Stub metrics for tests
        )

        # Token service for generating invitation tokens - must be mocked
        token_service = pretend.stub(
            dumps=pretend.call_recorder(lambda data: "fake-token"),
            max_age=300,  # 5 minutes
        )

        def find_service(iface, name=None, context=None, **kw):
            if iface.__name__ == "IUserService":
                return user_service
            elif iface.__name__ == "IOrganizationService":
                return organization_service
            elif name == "email":
                return token_service
            return None  # pragma: no cover

        return find_service, organization_service

    return create_services
