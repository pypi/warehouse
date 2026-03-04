# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

import pytest

from tests.common.constants import REMOTE_ADDR
from tests.common.db.accounts import UserFactory, UserUniqueLoginFactory
from tests.common.db.ip_addresses import IpAddressFactory
from tests.common.db.organizations import (
    OrganizationFactory,
    OrganizationInvitationFactory,
    OrganizationRoleFactory,
)
from warehouse.accounts.models import UniqueLoginStatus
from warehouse.admin.flags import AdminFlag, AdminFlagValue
from warehouse.organizations.models import OrganizationRoleType
from warehouse.utils.otp import _get_totp


@pytest.fixture
def _enable_organizations_functional(webtest):
    """Enable organizations management in functional tests"""
    db_sess = webtest.extra_environ["warehouse.db_session"]
    flag = db_sess.get(AdminFlag, AdminFlagValue.DISABLE_ORGANIZATIONS.value)
    original = flag.enabled
    flag.enabled = False
    yield
    flag.enabled = original


@pytest.mark.usefixtures("_enable_organizations_functional")
class TestManageOrganizationRoles:
    def _login_user(self, webtest, user):
        """Log in a user with 2FA and pre-confirmed IP."""
        ip_address = IpAddressFactory.create(ip_address=REMOTE_ADDR)
        UserUniqueLoginFactory.create(
            user=user,
            ip_address=ip_address,
            status=UniqueLoginStatus.CONFIRMED,
        )

        login_page = webtest.get("/account/login/", status=HTTPStatus.OK)
        login_form = login_page.forms["login-form"]
        login_form["username"] = user.username
        login_form["password"] = "password"

        two_factor_page = login_form.submit().follow(status=HTTPStatus.OK)
        two_factor_form = two_factor_page.forms["totp-auth-form"]
        two_factor_form["totp_value"] = (
            _get_totp(user.totp_secret).generate(time.time()).decode()
        )
        two_factor_form.submit().follow(status=HTTPStatus.OK)

    def test_member_cannot_invite_user_as_owner(self, webtest):
        """
        A member of an organization should not be able to invite other users,
        as they lack the OrganizationsManage permission. Only owners can invite.
        """
        # Arrange: Create org owner
        owner = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )

        # Create org member (who will attempt the invite)
        member = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )

        # Create target user (unrelated to the org, the one being invited)
        target = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
        )

        # Create organization with an owner and a member
        organization = OrganizationFactory.create(name="test-org")
        OrganizationRoleFactory.create(
            user=owner,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            user=member,
            organization=organization,
            role_name=OrganizationRoleType.Member,
        )

        # Act: Log in as the member
        self._login_user(webtest, member)

        # Navigate to org roles page — member can GET this (OrganizationsRead)
        roles_page = webtest.get(
            f"/manage/organization/{organization.normalized_name}/people/",
            status=HTTPStatus.OK,
        )

        # Extract CSRF token from the page
        csrf_input = roles_page.html.find("input", {"name": "csrf_token"})
        logged_in_csrf_token = csrf_input["value"]

        # POST to invite the target user as Owner — member should NOT be
        # able to do this, as inviting requires OrganizationsManage permission.
        webtest.post(
            f"/manage/organization/{organization.normalized_name}/people/",
            {
                "csrf_token": logged_in_csrf_token,
                "username": target.username,
                "role_name": "Owner",
            },
            status=HTTPStatus.FORBIDDEN,
        )

    def test_get_organization_roles(self, webtest):
        """
        Visit the Organization's People page
        and ensure that the database query count is reasonable.
        """
        # Create the owner who will view the page
        owner = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        organization = OrganizationFactory.create(name="test-org")
        OrganizationRoleFactory.create(
            user=owner,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        # Add several members to exercise the roles iteration
        for _ in range(3):
            member = UserFactory.create(
                with_verified_primary_email=True,
                with_terms_of_service_agreement=True,
            )
            OrganizationRoleFactory.create(
                user=member,
                organization=organization,
                role_name=OrganizationRoleType.Member,
            )

        # Add an invitation to exercise the invitations iteration
        invited_user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
        )
        OrganizationInvitationFactory.create(
            user=invited_user,
            organization=organization,
        )

        self._login_user(webtest, owner)

        # GET the organization roles page
        resp = webtest.get(
            f"/manage/organization/{organization.normalized_name}/people/",
            status=HTTPStatus.OK,
        )

        assert resp.status_code == HTTPStatus.OK
        assert len(webtest.query_recorder.queries) == 13
