# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

import pytest

from tests.common.constants import REMOTE_ADDR
from tests.common.db.accounts import UserFactory, UserUniqueLoginFactory
from tests.common.db.ip_addresses import IpAddressFactory
from tests.common.db.organizations import OrganizationFactory, OrganizationRoleFactory
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
        ip_address = IpAddressFactory.create(ip_address=REMOTE_ADDR)
        UserUniqueLoginFactory.create(
            user=member, ip_address=ip_address, status=UniqueLoginStatus.CONFIRMED
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
        login_page = webtest.get("/account/login/", status=HTTPStatus.OK)
        login_form = login_page.forms["login-form"]
        csrf_token = login_form["csrf_token"].value
        login_form["username"] = member.username
        login_form["password"] = "password"

        # Handle 2FA
        two_factor_page = login_form.submit().follow(status=HTTPStatus.OK)
        two_factor_form = two_factor_page.forms["totp-auth-form"]
        two_factor_form["csrf_token"] = csrf_token
        two_factor_form["totp_value"] = (
            _get_totp(member.totp_secret).generate(time.time()).decode()
        )
        two_factor_form.submit().follow(status=HTTPStatus.OK)

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
