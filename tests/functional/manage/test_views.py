# SPDX-License-Identifier: Apache-2.0

import time

from http import HTTPStatus

import faker
import pretend
import pytest

from webob.multidict import MultiDict

from warehouse.accounts.interfaces import IPasswordBreachedService, IUserService
from warehouse.accounts.models import UniqueLoginStatus
from warehouse.manage import views
from warehouse.manage.views import organizations as org_views
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import OrganizationType
from warehouse.utils.otp import _get_totp

from ...common.db.accounts import EmailFactory, UserFactory, UserUniqueLoginFactory


class TestManageAccount:
    def test_save_account(self, pyramid_services, user_service, db_request):
        breach_service = pretend.stub()
        organization_service = pretend.stub()
        pyramid_services.register_service(user_service, IUserService, None)
        pyramid_services.register_service(
            breach_service, IPasswordBreachedService, None
        )
        pyramid_services.register_service(
            organization_service, IOrganizationService, None
        )
        user = UserFactory.create(name="old name")
        EmailFactory.create(primary=True, verified=True, public=True, user=user)
        db_request.user = user
        db_request.method = "POST"
        db_request.path = "/manage/accounts/"
        db_request.POST = MultiDict({"name": "new name", "public_email": ""})

        views.ManageVerifiedAccountViews(db_request).save_account()
        user = user_service.get_user(user.id)

        assert user.name == "new name"
        assert user.public_email is None

    def test_changing_password_succeeds(self, webtest, socket_enabled):
        """A user can log in, and change their password."""
        # create a User
        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            clear_pwd="password",
        )
        UserUniqueLoginFactory.create(
            user=user, ip_address="1.2.3.4", status=UniqueLoginStatus.CONFIRMED
        )

        # visit login page
        login_page = webtest.get("/account/login/", status=HTTPStatus.OK)

        # Fill & submit the login form
        login_form = login_page.forms["login-form"]
        anonymous_csrf_token = login_form["csrf_token"].value
        login_form["username"] = user.username
        login_form["password"] = "password"
        login_form["csrf_token"] = anonymous_csrf_token

        two_factor_page = login_form.submit().follow(status=HTTPStatus.OK)

        two_factor_form = two_factor_page.forms["totp-auth-form"]
        two_factor_form["csrf_token"] = anonymous_csrf_token

        # Generate the correct TOTP value from the known secret
        two_factor_form["totp_value"] = (
            _get_totp(user.totp_secret).generate(time.time()).decode()
        )

        logged_in = two_factor_form.submit().follow(status=HTTPStatus.OK)
        assert logged_in.html.find(
            "title", string="Warehouse · The Python Package Index"
        )

        # Now visit the change password page
        change_password_page = logged_in.goto("/manage/account/", status=HTTPStatus.OK)

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

        # Request the JavaScript-enabled flash messages directly to get the message
        resp = webtest.get("/_includes/unauthed/flash-messages/", status=HTTPStatus.OK)
        success_message = resp.html.find("span", {"class": "notification-bar__message"})
        assert success_message.text == "Password updated"


class TestManageOrganizations:
    @pytest.mark.usefixtures("_enable_organizations")
    def test_create_organization_application(
        self,
        pyramid_services,
        user_service,
        organization_service,
        db_request,
        monkeypatch,
    ):
        pyramid_services.register_service(user_service, IUserService, None)
        pyramid_services.register_service(
            organization_service, IOrganizationService, None
        )
        user = UserFactory.create(name="old name")
        EmailFactory.create(primary=True, verified=True, public=True, user=user)
        db_request.user = user
        db_request.organization_access = True
        db_request.method = "POST"
        db_request.path = "/manage/organizations/"
        db_request.POST = MultiDict(
            {
                "name": "psf",
                "display_name": "Python Software Foundation",
                "orgtype": "Community",
                "link_url": "https://www.python.org/psf/",
                "description": (
                    "To promote, protect, and advance the Python programming "
                    "language, and to support and facilitate the growth of a "
                    "diverse and international community of Python programmers"
                ),
                "usage": ("We plan to host projects owned by the PSF"),
                "membership_size": "2-5",
            }
        )
        db_request.registry.settings[
            "warehouse.organizations.max_undecided_organization_applications"
        ] = 3
        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            org_views, "send_new_organization_requested_email", send_email
        )

        org_views.ManageOrganizationsViews(db_request).create_organization_application()
        organization_application = (
            organization_service.get_organization_applications_by_name(
                db_request.POST["name"]
            )
        )[0]

        assert organization_application.name == db_request.POST["name"]
        assert organization_application.display_name == db_request.POST["display_name"]
        assert (
            organization_application.orgtype
            == OrganizationType[db_request.POST["orgtype"]]
        )
        assert organization_application.link_url == db_request.POST["link_url"]
        assert organization_application.description == db_request.POST["description"]
        assert organization_application.submitted_by == user
