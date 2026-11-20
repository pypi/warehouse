# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

import faker

from sqlalchemy import select
from webtest import TestResponse
from webtest.forms import Form

from warehouse.organizations.models import (
    OrganizationApplication,
    OrganizationApplicationStatus,
    OrganizationMembershipSize,
    OrganizationType,
)

from ...common.db.accounts import UserFactory


def _find_form(page: TestResponse, *fields: str) -> Form:
    """
    Return the one form on the page that has all of the given fields.

    WebTest indexes each form by position, and again by id when it has one,
    so only the positional entries are searched.
    """
    (form,) = (
        form
        for index, form in page.forms.items()
        if isinstance(index, int) and all(field in form.fields for field in fields)
    )
    return form


class TestManageAccount:
    def test_save_account(self, webtest, login_user, flash_messages):
        """A user can change their name and hide their public email."""
        user = UserFactory.create(
            name="old name",
            with_verified_primary_email=True,
            email__public=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        assert user.public_email is not None
        login_user(user)

        account_page = webtest.get("/manage/account/", status=HTTPStatus.OK)
        save_account_form = _find_form(account_page, "name", "public_email")
        save_account_form["name"] = "new name"
        save_account_form["public_email"] = ""

        saved = save_account_form.submit(status=HTTPStatus.SEE_OTHER)
        assert saved.location.endswith("/manage/account/")
        assert flash_messages() == [("success", "Account details updated")]

        db_session = webtest.extra_environ["warehouse.db_session"]
        db_session.flush()
        db_session.expire_all()
        assert user.name == "new name"
        assert user.public_email is None

    def test_changing_password_succeeds(self, webtest, login_user, flash_messages):
        """A user can log in, and change their password."""
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )

        login_page = webtest.get("/account/login/", status=HTTPStatus.OK)
        anonymous_csrf_token = login_page.forms["login-form"]["csrf_token"].value

        login_user(user)

        # Now visit the change password page
        change_password_page = webtest.get("/manage/account/", status=HTTPStatus.OK)

        # Ensure that the CSRF token changes once logged in and a session is established
        logged_in_csrf_token = change_password_page.html.find(
            "input", {"name": "csrf_token"}
        )["value"]
        assert anonymous_csrf_token != logged_in_csrf_token

        # Fill & submit the change password form
        new_password = faker.Faker().password()  # a secure-enough password for testing
        change_password_form = change_password_page.forms["change-password-form"]
        change_password_form["csrf_token"] = logged_in_csrf_token
        change_password_form["password"] = "password"
        change_password_form["new_password"] = new_password
        change_password_form["password_confirm"] = new_password

        change_password_form.submit().follow(status=HTTPStatus.OK)

        assert flash_messages() == [("success", "Password updated")]


class TestManageOrganizations:
    def test_create_organization_application(self, webtest, login_user, flash_messages):
        """A user can request a new organization."""
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        login_user(user)

        organizations_page = webtest.get("/manage/organizations/", status=HTTPStatus.OK)
        application_form = _find_form(organizations_page, "membership_size")
        description = (
            "To promote, protect, and advance the Python programming "
            "language, and to support and facilitate the growth of a "
            "diverse and international community of Python programmers"
        )
        application_form["name"] = "psf"
        application_form["display_name"] = "Python Software Foundation"
        application_form["orgtype"] = "Community"
        application_form["link_url"] = " https://www.python.org/psf/ "
        application_form["description"] = description
        application_form["usage"] = "We plan to host projects owned by the PSF"
        application_form["membership_size"] = "2-5"

        submitted = application_form.submit(status=HTTPStatus.SEE_OTHER)
        assert submitted.location.endswith("/manage/organizations/")
        assert flash_messages() == [
            ("success", "Request for new organization submitted")
        ]

        db_session = webtest.extra_environ["warehouse.db_session"]
        db_session.flush()
        db_session.expire_all()
        organization_application = db_session.scalars(
            select(OrganizationApplication).where(OrganizationApplication.name == "psf")
        ).one()
        assert organization_application.normalized_name == "psf"
        assert organization_application.display_name == "Python Software Foundation"
        assert organization_application.orgtype == OrganizationType.Community
        assert organization_application.link_url == "https://www.python.org/psf/"
        assert organization_application.description == description
        assert organization_application.usage == (
            "We plan to host projects owned by the PSF"
        )
        assert (
            organization_application.membership_size == OrganizationMembershipSize.smol
        )
        assert (
            organization_application.status == OrganizationApplicationStatus.Submitted
        )
        assert organization_application.submitted_by == user
