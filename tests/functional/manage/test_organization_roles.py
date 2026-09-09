# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

from tests.common.constants import REMOTE_ADDR
from tests.common.db.accounts import UserFactory, UserUniqueLoginFactory
from tests.common.db.ip_addresses import IpAddressFactory
from tests.common.db.organizations import (
    OrganizationFactory,
    OrganizationInvitationFactory,
    OrganizationRoleFactory,
    OrganizationStripeSubscriptionFactory,
)
from tests.common.db.subscriptions import StripeSubscriptionFactory
from warehouse.accounts.models import UniqueLoginStatus
from warehouse.organizations.models import OrganizationRoleType, OrganizationType
from warehouse.subscriptions.models import StripeSubscriptionStatus
from warehouse.utils.otp import _get_totp


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

    def _create_owner_and_target(self):
        """Create an org owner and a target user to invite."""
        owner = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        target = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
        )
        return owner, target

    def _post_invite(
        self, webtest, organization, target_username, role_name, csrf_token
    ):
        """POST an invitation and return the response."""
        return webtest.post(
            f"/manage/organization/{organization.normalized_name}/people/",
            {
                "csrf_token": csrf_token,
                "username": target_username,
                "role_name": role_name,
            },
        )

    def _get_roles_page(self, webtest, organization, status=HTTPStatus.OK):
        """GET the organization roles page."""
        return webtest.get(
            f"/manage/organization/{organization.normalized_name}/people/",
            status=status,
        )

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
        assert "Invite member" in resp.text

    def test_new_company_org_can_access_roles_page(self, webtest):
        """
        A newly approved Company org without billing can access the roles page.
        """
        owner, _ = self._create_owner_and_target()
        organization = OrganizationFactory.create(
            name="new-company-org", orgtype=OrganizationType.Company
        )
        OrganizationRoleFactory.create(
            user=owner,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        self._login_user(webtest, owner)

        roles_page = self._get_roles_page(webtest, organization, status=HTTPStatus.OK)
        assert "Invite member" in roles_page.text
        assert "Billing not yet activated" in roles_page.text

    def test_new_company_org_can_invite_billing_manager(self, webtest):
        """
        A newly approved Company org without billing can invite a Billing Manager.
        """
        owner, target = self._create_owner_and_target()
        organization = OrganizationFactory.create(
            name="new-company-org", orgtype=OrganizationType.Company
        )
        OrganizationRoleFactory.create(
            user=owner,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        self._login_user(webtest, owner)

        roles_page = self._get_roles_page(webtest, organization, status=HTTPStatus.OK)
        csrf_input = roles_page.html.find("input", {"name": "csrf_token"})
        csrf_token = csrf_input["value"]

        resp = self._post_invite(
            webtest, organization, target.username, "Billing Manager", csrf_token
        )
        assert resp.status_code == HTTPStatus.SEE_OTHER

        # Check the flash message through the JavaScript endpoint.
        flash_messages = webtest.get(
            "/_includes/unauthed/flash-messages/", status=HTTPStatus.OK
        )
        success_message = flash_messages.html.find(
            "span", {"class": "notification-bar__message"}
        )
        assert success_message is not None
        assert "Invitation sent" in success_message.text

    def test_new_company_org_cannot_invite_other_roles(self, webtest):
        """
        A newly approved Company org without billing cannot invite
        Owner, Manager, or Member.
        """
        owner, target = self._create_owner_and_target()
        organization = OrganizationFactory.create(
            name="new-company-org", orgtype=OrganizationType.Company
        )
        OrganizationRoleFactory.create(
            user=owner,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        self._login_user(webtest, owner)

        roles_page = self._get_roles_page(webtest, organization, status=HTTPStatus.OK)
        csrf_input = roles_page.html.find("input", {"name": "csrf_token"})
        csrf_token = csrf_input["value"]

        role_select = roles_page.html.find("select", {"name": "role_name"})
        assert role_select is not None, "role_name select not found"

        role_choices = [
            option.get("value")
            for option in role_select.find_all("option")
            if option.get("value")
        ]

        assert role_choices == ["Billing Manager"]

        resp = self._post_invite(
            webtest, organization, target.username, "Owner", csrf_token
        )
        assert resp.status_code == HTTPStatus.OK
        assert "Not a valid choice" in resp.text

    def test_company_org_with_lapsed_subscription_blocked(self, webtest):
        """
        A Company org with a lapsed (canceled) subscription is blocked
        from the roles page.
        """
        owner, _ = self._create_owner_and_target()
        organization = OrganizationFactory.create(
            name="lapsed-company-org", orgtype=OrganizationType.Company
        )
        OrganizationRoleFactory.create(
            user=owner,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )
        subscription = StripeSubscriptionFactory.create(
            status=StripeSubscriptionStatus.Canceled.value
        )

        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )

        self._login_user(webtest, owner)

        resp = self._get_roles_page(webtest, organization, status=HTTPStatus.SEE_OTHER)
        assert resp.location.endswith("/manage/organizations/")

    def test_company_org_with_active_subscription_works(self, webtest):
        """
        A Company org with an active subscription works normally (all roles available).
        """
        owner, _ = self._create_owner_and_target()
        organization = OrganizationFactory.create(
            name="active-company-org", orgtype=OrganizationType.Company
        )
        OrganizationRoleFactory.create(
            user=owner,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )
        subscription = StripeSubscriptionFactory.create(
            status=StripeSubscriptionStatus.Active.value
        )

        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )

        self._login_user(webtest, owner)

        roles_page = self._get_roles_page(webtest, organization, status=HTTPStatus.OK)
        assert "Invite member" in roles_page.text
        assert "Billing Notice" in roles_page.text
        assert "Billing not yet activated" not in roles_page.text

        role_select = roles_page.html.find("select", {"name": "role_name"})
        assert role_select is not None, "role_name select not found"

        role_choices = [
            option.get("value")
            for option in role_select.find_all("option")
            if option.get("value")
        ]

        assert set(role_choices) == {
            "Member",
            "Manager",
            "Owner",
            "Billing Manager",
        }

    def test_community_org_works_normally(self, webtest):
        """
        A Community org works normally (no billing restrictions).
        """
        owner, _ = self._create_owner_and_target()
        organization = OrganizationFactory.create(
            name="community-org", orgtype=OrganizationType.Community
        )
        OrganizationRoleFactory.create(
            user=owner,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        self._login_user(webtest, owner)

        roles_page = self._get_roles_page(webtest, organization, status=HTTPStatus.OK)
        assert "Invite member" in roles_page.text
        role_select = roles_page.html.find("select", {"name": "role_name"})
        assert role_select is not None, "role_name select not found"

        role_choices = [
            option.get("value")
            for option in role_select.find_all("option")
            if option.get("value")
        ]

        assert set(role_choices) == {"Member", "Manager", "Owner"}

    def test_deactivated_company_org_blocked(self, webtest):
        """
        A deactivated Company org is blocked from the roles page.
        """
        owner, _ = self._create_owner_and_target()
        organization = OrganizationFactory.create(
            name="deactivated-company-org",
            orgtype=OrganizationType.Company,
            is_active=False,
        )
        OrganizationRoleFactory.create(
            user=owner,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        self._login_user(webtest, owner)

        resp = self._get_roles_page(webtest, organization, status=HTTPStatus.SEE_OTHER)
        assert resp.location.endswith("/manage/organizations/")
