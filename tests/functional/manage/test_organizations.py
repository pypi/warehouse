# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

from tests.common.constants import REMOTE_ADDR
from tests.common.db.accounts import UserFactory, UserUniqueLoginFactory
from tests.common.db.ip_addresses import IpAddressFactory
from tests.common.db.organizations import (
    OrganizationFactory,
    OrganizationRoleFactory,
)
from warehouse.accounts.models import UniqueLoginStatus
from warehouse.organizations.models import OrganizationRoleType, OrganizationType
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

    def test_owner_can_reach_settings_when_billing_inactive(self, webtest):
        """
        An owner of a Company organization that is not in good standing (no
        active subscription or manual activation) can still reach the
        organization settings page, so they are able to delete it. Otherwise
        the only self-service exit would be to first pay to reactivate billing.
        """
        owner = UserFactory.create(
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
            user=owner,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

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
        owner = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        organization = OrganizationFactory.create(
            name="billing-inactive-org",
            orgtype=OrganizationType.Company,
        )
        assert not organization.is_in_good_standing()
        OrganizationRoleFactory.create(
            user=owner,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        self._login_user(webtest, owner)

        list_page = webtest.get("/manage/organizations/", status=HTTPStatus.OK)
        manage_url = f"/manage/organization/{organization.normalized_name}/settings/"
        assert manage_url in list_page.text
