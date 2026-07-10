# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

import pytest

from tests.common.constants import REMOTE_ADDR
from tests.common.db import Session
from tests.common.db.accounts import UserFactory, UserUniqueLoginFactory
from tests.common.db.ip_addresses import IpAddressFactory
from tests.common.db.organizations import (
    OrganizationFactory,
    OrganizationRoleFactory,
    OrganizationStripeSubscriptionFactory,
)
from tests.common.db.subscriptions import StripeSubscriptionFactory
from warehouse.accounts.models import UniqueLoginStatus
from warehouse.organizations.models import (
    Organization,
    OrganizationRoleType,
    OrganizationType,
)
from warehouse.subscriptions.models import StripeSubscriptionStatus
from warehouse.utils.otp import _get_totp


class TestManageOrganizationSettings:
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

    def _create_billing_inactive_org(self, role_name=OrganizationRoleType.Owner):
        """Create a Company org not in good standing and a user with a role in it."""
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        # Company org with no billing is not in good standing.
        organization = OrganizationFactory.create(
            name="billing-inactive-org",
            orgtype=OrganizationType.Company,
        )
        assert not organization.is_in_good_standing()
        OrganizationRoleFactory.create(
            user=user,
            organization=organization,
            role_name=role_name,
        )
        return user, organization

    def _post_delete_organization(self, webtest, organization, status):
        """GET the settings page for a CSRF token, then POST the delete confirmation."""
        settings_url = f"/manage/organization/{organization.normalized_name}/settings/"
        settings_page = webtest.get(settings_url, status=HTTPStatus.OK)
        csrf_token = settings_page.html.find("input", {"name": "csrf_token"})["value"]

        return webtest.post(
            settings_url,
            {
                "csrf_token": csrf_token,
                "confirm_organization_name": organization.name,
            },
            status=status,
        )

    def test_owner_can_reach_settings_when_billing_inactive(self, webtest):
        """
        An owner of a Company organization that is not in good standing (no
        active subscription or manual activation) can still reach the
        organization settings page, so they are able to delete it. Otherwise
        the only self-service exit would be to first pay to reactivate billing.
        """
        owner, organization = self._create_billing_inactive_org()

        self._login_user(webtest, owner)

        settings_page = webtest.get(
            f"/manage/organization/{organization.normalized_name}/settings/",
            status=HTTPStatus.OK,
        )
        assert "Delete organization" in settings_page.text

    def test_org_list_shows_manage_link_when_billing_inactive(self, webtest):
        """
        The organizations list offers owners a "Manage" link to the settings
        page even when billing is inactive, so they can reach the delete flow.
        """
        owner, organization = self._create_billing_inactive_org()

        self._login_user(webtest, owner)

        list_page = webtest.get("/manage/organizations/", status=HTTPStatus.OK)
        manage_url = f"/manage/organization/{organization.normalized_name}/settings/"
        assert manage_url in list_page.text

    def test_publishing_page_redirects_when_billing_inactive(self, webtest):
        """
        The trusted publishing page is gated behind good standing: an owner of
        a Company organization with inactive billing is redirected back to the
        organizations list instead.
        """
        owner, organization = self._create_billing_inactive_org()

        self._login_user(webtest, owner)

        response = webtest.get(
            f"/manage/organization/{organization.normalized_name}/publishing/",
            status=HTTPStatus.SEE_OTHER,
        )
        assert response.location.endswith("/manage/organizations/")

    def test_owner_can_delete_org_while_billing_inactive(self, webtest):
        """
        An owner of an empty Company organization with no billing can POST the
        delete confirmation and the organization is actually deleted.
        """
        owner, organization = self._create_billing_inactive_org()
        organization_id = organization.id

        self._login_user(webtest, owner)

        response = self._post_delete_organization(
            webtest, organization, status=HTTPStatus.SEE_OTHER
        )
        assert response.location.endswith("/manage/organizations/")
        assert Session.get(Organization, organization_id) is None

    def test_owner_can_delete_org_with_canceled_subscription(self, webtest):
        """
        An organization whose Stripe subscription was canceled is not in good
        standing, but its owner can still delete it.
        """
        owner, organization = self._create_billing_inactive_org()
        subscription = StripeSubscriptionFactory.create(
            status=StripeSubscriptionStatus.Canceled,
            subscription_id="sub_1234567890",
        )
        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )
        assert not organization.is_in_good_standing()
        organization_id = organization.id

        self._login_user(webtest, owner)

        response = self._post_delete_organization(
            webtest, organization, status=HTTPStatus.SEE_OTHER
        )
        assert response.location.endswith("/manage/organizations/")
        assert Session.get(Organization, organization_id) is None

    @pytest.mark.parametrize(
        "role_name",
        [OrganizationRoleType.BillingManager, OrganizationRoleType.Member],
    )
    def test_non_owners_cannot_delete_while_billing_inactive(self, webtest, role_name):
        """
        Billing managers and members can view the settings page (it only
        requires OrganizationsRead), but lack OrganizationsManage, so POSTing
        the delete confirmation for a billing-inactive organization is
        forbidden.
        """
        user, organization = self._create_billing_inactive_org(role_name=role_name)

        self._login_user(webtest, user)

        self._post_delete_organization(
            webtest, organization, status=HTTPStatus.FORBIDDEN
        )
        assert Session.get(Organization, organization.id) is not None
