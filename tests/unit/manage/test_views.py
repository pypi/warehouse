# SPDX-License-Identifier: Apache-2.0

import base64
import datetime as dt
import time
import uuid

import pretend
import pytest

from freezegun import freeze_time
from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPNotFound,
    HTTPOk,
    HTTPSeeOther,
)
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import joinedload
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.structs import AttestationFormat, PublicKeyCredentialType
from webauthn.registration.verify_registration_response import VerifiedRegistration
from webob.multidict import MultiDict

from warehouse.accounts.forms import RecoveryCodeAuthenticationForm
from warehouse.accounts.interfaces import (
    IPasswordBreachedService,
    ITokenService,
    IUserService,
)
from warehouse.accounts.models import Email, WebAuthn
from warehouse.accounts.services import (
    RECOVERY_CODE_BYTES,
    RECOVERY_CODE_COUNT,
    NullPasswordBreachedService,
    TokenService,
)
from warehouse.admin.flags import AdminFlagValue
from warehouse.constants import MAX_FILESIZE, MAX_PROJECT_SIZE
from warehouse.events.tags import EventTag
from warehouse.macaroons import caveats
from warehouse.macaroons.models import Macaroon
from warehouse.manage import views
from warehouse.manage.forms import CreateMacaroonForm, DeleteMacaroonForm
from warehouse.manage.views import (
    organizations as org_views,
    view_helpers,
)
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import (
    OrganizationRoleType,
    OrganizationType,
    TeamProjectRole,
    TeamProjectRoleType,
)
from warehouse.packaging.models import (
    File,
    JournalEntry,
    LifecycleStatus,
    Project,
    Release,
    Role,
    RoleInvitation,
    RoleInvitationStatus,
    User,
)
from warehouse.rate_limiting import IRateLimiter, RateLimiter
from warehouse.sessions import Session
from warehouse.utils import otp
from warehouse.utils.paginate import paginate_url_factory
from warehouse.utils.project import (
    DELETE_FILE_ACKNOWLEDGMENTS,
    DELETE_PROJECT_ACKNOWLEDGMENTS,
    DELETE_RELEASE_ACKNOWLEDGMENTS,
)

from ...common.db.accounts import (
    EmailFactory,
    OAuthAccountAssociationFactory,
    RecoveryCodeFactory,
    UserFactory,
    WebAuthnFactory,
)
from ...common.db.macaroons import MacaroonFactory
from ...common.db.organizations import (
    OrganizationFactory,
    OrganizationProjectFactory,
    OrganizationRoleFactory,
    TeamFactory,
    TeamProjectRoleFactory,
    TeamRoleFactory,
)
from ...common.db.packaging import (
    FileEventFactory,
    FileFactory,
    JournalEntryFactory,
    ProjectEventFactory,
    ProjectFactory,
    ReleaseFactory,
    RoleFactory,
    RoleInvitationFactory,
)


@pytest.fixture
def limiters(pyramid_services, mocker):
    """
    Autospec'd per-IP ``email.add``, per-user ``email.change`` and per-user
    ``email.verify`` rate limiters, registered one per name, all allowing by
    default.
    """
    limiters = {}
    for name in ("email.add", "email.change", "email.verify"):
        limiter = mocker.create_autospec(RateLimiter, instance=True)
        limiter.test.return_value = True
        limiter.hit.return_value = True
        pyramid_services.register_service(limiter, IRateLimiter, None, name=name)
        limiters[name] = limiter
    return limiters


@pytest.fixture
def breach_service(pyramid_services):
    service = NullPasswordBreachedService()
    pyramid_services.register_service(service, IPasswordBreachedService, None)
    return service


@pytest.fixture
def post_request(db_request, breach_service, limiters, mocker):
    """
    A POST with an empty body and no user yet, with ``route_path`` echoing the
    route name and ``session.flash`` spied. Tests attach the user they need.
    """
    db_request.method = "POST"
    db_request.POST = MultiDict()
    mocker.patch.object(
        db_request,
        "route_path",
        autospec=True,
        side_effect=lambda name: f"/{name}/",
    )
    mocker.spy(db_request.session, "flash")
    return db_request


@pytest.fixture
def verified_request(post_request):
    """``post_request`` from a user with a verified primary email and TOTP."""
    post_request.user = UserFactory.create(with_verified_primary_email=True)
    return post_request


@pytest.fixture
def user_password(verified_request, user_service):
    """
    Give the ``verified_request`` user a real, hashed password and return the
    cleartext. Only tests that check a submitted password need the hashing.
    """
    password = "password"
    user_service.update_user(verified_request.user.id, password=password)
    return password


@pytest.fixture
def real_session_request(verified_request, mocker):
    """
    ``verified_request`` with a real ``Session``, which has the password
    timestamp, TOTP secret and WebAuthn challenge methods ``DummySession``
    lacks.
    """
    verified_request.session = Session()
    mocker.spy(verified_request.session, "flash")
    return verified_request


@pytest.fixture
def two_factor_request(pyramid_config, real_session_request):
    """
    ``real_session_request`` with a burned recovery code and a site name.
    ``pyramid_config`` is requested first because it replaces the registry the
    site name is written to.
    """
    real_session_request.registry.settings["site.name"] = "PyPI"
    RecoveryCodeFactory.create(
        user=real_session_request.user, burned=dt.datetime.now(dt.UTC)
    )
    return real_session_request


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("42", 42),
        (str(2**31 - 1), 2**31 - 1),
        (str(-(2**31)), -(2**31)),
        (str(2**31), None),
        (str(-(2**31) - 1), None),
        ("nope", None),
        (object(), None),
    ],
)
def test_parse_email_id(value, expected):
    assert views._parse_email_id(value) == expected


class TestManageUnverifiedAccount:
    @pytest.fixture
    def unverified_request(self, post_request):
        """
        ``post_request`` from a user with no verified primary email, no
        two-factor and no projects, changing their email address.
        """
        post_request.user = UserFactory.create(totp_secret=None)
        post_request.POST.update(
            {
                "change_unverified_primary_email": "1",
                "email": "correct@example.com",
            }
        )
        return post_request

    def test_manage_account(self, unverified_request, user_service):
        view = views.ManageUnverifiedAccountViews(unverified_request)

        assert view.manage_unverified_account() == {
            "docs_url": "https://docs.pypi.org/your-account/account-recovery/",
        }
        assert view.request is unverified_request
        assert view.user_service is user_service

    def test_verified_redirects(self, verified_request):
        view = views.ManageUnverifiedAccountViews(verified_request)

        result = view.manage_unverified_account()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account/"

    @pytest.mark.usefixtures("no_email_deliverability_check")
    @pytest.mark.parametrize(
        ("has_old_primary", "expected_old_address"),
        [
            (True, "typo@exmaple.com"),  # codespell:ignore exmaple
            (False, None),
        ],
    )
    def test_change_unverified_primary_email(
        self,
        unverified_request,
        user_service,
        limiters,
        mocker,
        has_old_primary,
        expected_old_address,
    ):
        user = unverified_request.user
        old_email = (
            EmailFactory.create(
                user=user,
                email="typo@exmaple.com",  # codespell:ignore exmaple
                verified=False,
                primary=True,
            )
            if has_old_primary
            else None
        )
        add_email = mocker.spy(user_service, "add_email")
        delete = mocker.spy(unverified_request.db, "delete")
        record_event = mocker.spy(user, "record_event")
        send_email = mocker.patch.object(
            views, "send_email_verification_email", autospec=True
        )

        view = views.ManageUnverifiedAccountViews(unverified_request)
        result = view.change_unverified_primary_email()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.unverified-account/"
        add_email.assert_called_once_with(
            user.id, "correct@example.com", primary=True, ratelimit=False
        )
        new_email = add_email.spy_return
        if has_old_primary:
            delete.assert_called_once_with(old_email)
        else:
            delete.assert_not_called()
        unverified_request.db.flush()
        assert unverified_request.db.scalars(
            select(Email).where(Email.user_id == user.id)
        ).all() == [new_email]
        assert new_email.primary
        assert new_email.email == "correct@example.com"
        assert not new_email.verified
        limiters["email.change"].hit.assert_called_once_with(user.id)
        limiters["email.add"].hit.assert_called_once_with(
            unverified_request.remote_addr
        )
        send_email.assert_called_once_with(unverified_request, (user, new_email))
        record_event.assert_called_once_with(
            tag=EventTag.Account.EmailPrimaryChange,
            request=unverified_request,
            additional={
                "old_primary": expected_old_address,
                "new_primary": "correct@example.com",
            },
        )
        unverified_request.session.flash.assert_called_once_with(
            "Email address updated to correct@example.com - check your "
            "email for a verification link",
            queue="success",
        )

    def test_change_unverified_primary_email_validation_fails(
        self, unverified_request, user_service, limiters
    ):
        """A failed validation still spends the attempt budget."""
        unverified_request.POST["email"] = "bad"
        user = unverified_request.user

        view = views.ManageUnverifiedAccountViews(unverified_request)
        result = view.change_unverified_primary_email()

        form = result["change_unverified_primary_email_form"]
        assert result == {
            "docs_url": "https://docs.pypi.org/your-account/account-recovery/",
            "change_unverified_primary_email_form": form,
        }
        assert isinstance(form, views.ChangeUnverifiedPrimaryEmailForm)
        assert form.email.data == "bad"
        assert form.email.errors
        assert form.request is unverified_request
        assert form.user_service is user_service
        assert form.user_id == user.id
        limiters["email.change"].hit.assert_called_once_with(user.id)
        # The strict per-IP budget is only spent on a successful change.
        limiters["email.add"].hit.assert_not_called()

    def test_change_unverified_primary_email_attempt_rate_limited(
        self, unverified_request, limiters
    ):
        """Exhausting the attempt budget blocks before the form is validated."""
        limiters["email.change"].hit.return_value = False

        view = views.ManageUnverifiedAccountViews(unverified_request)
        result = view.change_unverified_primary_email()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.unverified-account/"
        unverified_request.session.flash.assert_called_once_with(
            "Too many email change attempts. Try again later.",
            queue="error",
        )
        limiters["email.change"].hit.assert_called_once_with(unverified_request.user.id)

    def test_change_unverified_primary_email_blocked_if_verified(
        self, verified_request
    ):
        view = views.ManageUnverifiedAccountViews(verified_request)
        result = view.change_unverified_primary_email()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account/"

    @pytest.mark.parametrize(
        ("has_two_factor", "has_project", "expected_message"),
        [
            (
                True,
                False,
                (
                    "Cannot change email address on accounts with two-factor "
                    "authentication enabled"
                ),
            ),
            (
                False,
                True,
                "Cannot change email address on accounts with projects",
            ),
        ],
    )
    def test_change_unverified_primary_email_blocked(
        self, post_request, has_two_factor, has_project, expected_message
    ):
        user = UserFactory.create(totp_secret=b"x" * 20 if has_two_factor else None)
        if has_project:
            RoleFactory.create(user=user)
        post_request.user = user
        view = views.ManageUnverifiedAccountViews(post_request)
        result = view.change_unverified_primary_email()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.unverified-account/"
        post_request.session.flash.assert_called_once_with(
            expected_message, queue="error"
        )

    def test_change_unverified_primary_email_ip_rate_limited(
        self, unverified_request, limiters
    ):
        limiters["email.add"].test.return_value = False

        view = views.ManageUnverifiedAccountViews(unverified_request)
        result = view.change_unverified_primary_email()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.unverified-account/"
        unverified_request.session.flash.assert_called_once_with(
            "Too many email change attempts. Try again later.",
            queue="error",
        )
        limiters["email.add"].test.assert_called_once_with(
            unverified_request.remote_addr
        )
        # Turned away before validation, so it doesn't cost the user an attempt.
        limiters["email.change"].hit.assert_not_called()


class TestManageAccount:
    @pytest.fixture
    def default_response(self, mocker):
        """
        Replace the real ``default_response``, which builds fresh forms on
        every access, with one opaque dict a test can compare against.
        """
        response = {"_": mocker.sentinel.default_response}
        mocker.patch.object(
            views.ManageVerifiedAccountViews, "default_response", response
        )
        return response

    @pytest.mark.parametrize(
        ("public_email", "expected_public_email"),
        [(None, ""), ("some@email.com", "some@email.com")],
    )
    def test_default_response(
        self,
        verified_request,
        user_service,
        breach_service,
        mocker,
        public_email,
        expected_public_email,
    ):
        user = verified_request.user
        if public_email is not None:
            EmailFactory.create(
                user=user, email=public_email, primary=False, public=True
            )
        association = OAuthAccountAssociationFactory.create(user=user)
        get_account_associations = mocker.spy(user_service, "get_account_associations")

        view = views.ManageVerifiedAccountViews(verified_request)
        result = view.default_response

        save_account_form = result["save_account_form"]
        add_email_form = result["add_email_form"]
        change_password_form = result["change_password_form"]
        assert result == {
            "save_account_form": save_account_form,
            "add_email_form": add_email_form,
            "change_password_form": change_password_form,
            "active_projects": [],
            "sole_organizations": [],
            "account_associations": [association],
        }
        assert view.request is verified_request
        assert view.user_service is user_service
        get_account_associations.assert_called_once_with(user.id)
        assert isinstance(save_account_form, views.SaveAccountForm)
        assert save_account_form.name.data == user.name
        assert save_account_form.public_email.data == expected_public_email
        assert save_account_form.user_service is user_service
        assert save_account_form.user_id == user.id
        assert isinstance(add_email_form, views.AddEmailForm)
        assert add_email_form.request is verified_request
        assert add_email_form.user_service is user_service
        assert add_email_form.user_id == user.id
        assert isinstance(change_password_form, views.ChangePasswordForm)
        assert change_password_form.request is verified_request
        assert change_password_form.user_service is user_service
        assert change_password_form._breach_service is breach_service

    def test_active_projects(self, post_request):
        user = UserFactory.create()
        another_user = UserFactory.create()

        post_request.user = user

        # A project with a sole owner that is the user
        with_sole_owner = ProjectFactory.create()
        RoleFactory.create(user=user, project=with_sole_owner, role_name="Owner")
        RoleFactory.create(
            user=another_user, project=with_sole_owner, role_name="Maintainer"
        )

        # A project with multiple owners, including the user
        with_multiple_owners = ProjectFactory.create()
        RoleFactory.create(user=user, project=with_multiple_owners, role_name="Owner")
        RoleFactory.create(
            user=another_user, project=with_multiple_owners, role_name="Owner"
        )

        # A project with a sole owner that is not the user
        not_an_owner = ProjectFactory.create()
        RoleFactory.create(user=user, project=not_an_owner, role_name="Maintainer")
        RoleFactory.create(user=another_user, project=not_an_owner, role_name="Owner")

        view = views.ManageVerifiedAccountViews(post_request)

        assert view.active_projects == [with_sole_owner]

    def test_manage_account(self, verified_request, user_service, default_response):
        view = views.ManageVerifiedAccountViews(verified_request)

        assert view.manage_account() == default_response
        assert view.request is verified_request
        assert view.user_service is user_service

    def test_save_account(self, verified_request, user_service, mocker):
        user = verified_request.user
        email = user.primary_email
        email.public = True
        verified_request.POST = MultiDict({"name": "new name", "public_email": ""})
        update_user = mocker.spy(user_service, "update_user")

        view = views.ManageVerifiedAccountViews(verified_request)
        result = view.save_account()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == verified_request.path
        verified_request.session.flash.assert_called_once_with(
            "Account details updated", queue="success"
        )
        # The view pops ``public_email`` and applies it to the emails itself.
        update_user.assert_called_once_with(user.id, name="new name")
        assert user.name == "new name"
        assert not email.public

    def test_save_account_validation_fails(
        self, verified_request, user_service, mocker, default_response
    ):
        user = verified_request.user
        name = user.name
        verified_request.POST = MultiDict({"name": "x" * 101, "public_email": ""})
        update_user = mocker.spy(user_service, "update_user")

        view = views.ManageVerifiedAccountViews(verified_request)
        result = view.save_account()

        form = result["save_account_form"]
        assert result == {**default_response, "save_account_form": form}
        assert isinstance(form, views.SaveAccountForm)
        assert form.name.errors
        verified_request.session.flash.assert_not_called()
        update_user.assert_not_called()
        assert user.name == name

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_add_email(self, verified_request, user_service, mocker):
        new_email_address = "new@example.com"
        user = verified_request.user
        existing_email = user.primary_email
        verified_request.POST = MultiDict({"email": new_email_address})
        add_email = mocker.spy(user_service, "add_email")
        record_event = mocker.spy(user, "record_event")
        send_email_verification_email = mocker.patch.object(
            views, "send_email_verification_email", autospec=True
        )
        send_new_email_added_email = mocker.patch.object(
            views, "send_new_email_added_email", autospec=True
        )

        view = views.ManageVerifiedAccountViews(verified_request)
        result = view.add_email()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == verified_request.path
        add_email.assert_called_once_with(user.id, new_email_address)
        email = add_email.spy_return
        assert email.email == new_email_address
        assert user.emails == [existing_email, email]
        verified_request.session.flash.assert_called_once_with(
            f"Email {new_email_address} added - check your email for "
            "a verification link",
            queue="success",
        )
        send_email_verification_email.assert_called_once_with(
            verified_request, (user, email)
        )
        send_new_email_added_email.assert_called_once_with(
            verified_request,
            (user, existing_email),
            new_email_address=new_email_address,
        )
        record_event.assert_called_once_with(
            tag=EventTag.Account.EmailAdd,
            request=verified_request,
            additional={"email": new_email_address},
        )

    def test_add_email_validation_fails(
        self, verified_request, user_service, mocker, default_response
    ):
        user = verified_request.user
        existing_email = user.primary_email
        verified_request.POST = MultiDict({"email": "bad"})
        add_email = mocker.spy(user_service, "add_email")

        view = views.ManageVerifiedAccountViews(verified_request)
        result = view.add_email()

        form = result["add_email_form"]
        assert result == {**default_response, "add_email_form": form}
        assert isinstance(form, views.AddEmailForm)
        assert form.email.errors
        add_email.assert_not_called()
        verified_request.db.flush()
        assert verified_request.db.scalars(
            select(Email).where(Email.user_id == user.id)
        ).all() == [existing_email]
        verified_request.session.flash.assert_not_called()

    def test_delete_email(self, verified_request, mocker):
        user = verified_request.user
        primary_email = user.primary_email
        email = EmailFactory.create(user=user, primary=False)
        email_address = email.email
        verified_request.POST = MultiDict({"delete_email_id": str(email.id)})
        record_event = mocker.spy(user, "record_event")

        view = views.ManageVerifiedAccountViews(verified_request)
        result = view.delete_email()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == verified_request.path
        verified_request.session.flash.assert_called_once_with(
            f"Email address {email_address} removed", queue="success"
        )
        assert user.emails == [primary_email]
        record_event.assert_called_once_with(
            tag=EventTag.Account.EmailRemove,
            request=verified_request,
            additional={"email": email_address},
        )
        verified_request.db.flush()
        assert verified_request.db.scalars(
            select(Email).where(Email.user_id == user.id)
        ).all() == [primary_email]

    @pytest.mark.parametrize("email_id", ["9999", "999999999999", "nope"])
    def test_delete_email_not_found(self, verified_request, default_response, email_id):
        primary = verified_request.user.primary_email
        verified_request.POST = MultiDict({"delete_email_id": email_id})

        view = views.ManageVerifiedAccountViews(verified_request)

        assert view.delete_email() == default_response
        verified_request.session.flash.assert_called_once_with(
            "Email address not found", queue="error"
        )
        assert verified_request.user.emails == [primary]

    def test_delete_email_is_primary(self, verified_request, default_response):
        user = verified_request.user
        email = user.primary_email
        verified_request.POST = MultiDict({"delete_email_id": str(email.id)})

        view = views.ManageVerifiedAccountViews(verified_request)

        assert view.delete_email() == default_response
        verified_request.session.flash.assert_called_once_with(
            "Cannot remove primary email address", queue="error"
        )
        assert user.emails == [email]

    def test_change_primary_email(self, post_request, mocker):
        user = UserFactory.create()
        old_primary = EmailFactory.create(primary=True, user=user, email="old")
        new_primary = EmailFactory.create(
            primary=False, verified=True, user=user, email="new"
        )
        post_request.user = user
        post_request.POST = MultiDict({"primary_email_id": str(new_primary.id)})
        record_event = mocker.spy(user, "record_event")
        send_email = mocker.patch.object(
            views, "send_primary_email_change_email", autospec=True
        )

        view = views.ManageVerifiedAccountViews(post_request)
        result = view.change_primary_email()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == post_request.path
        send_email.assert_called_once_with(post_request, (user, old_primary))
        post_request.session.flash.assert_called_once_with(
            f"Email address {new_primary.email} set as primary", queue="success"
        )
        assert not old_primary.primary
        assert new_primary.primary
        record_event.assert_called_once_with(
            tag=EventTag.Account.EmailPrimaryChange,
            request=post_request,
            additional={"old_primary": "old", "new_primary": "new"},
        )

    def test_change_primary_email_without_current(self, post_request, mocker):
        user = UserFactory.create()
        new_primary = EmailFactory.create(primary=False, verified=True, user=user)
        post_request.user = user
        post_request.POST = MultiDict({"primary_email_id": str(new_primary.id)})
        record_event = mocker.spy(user, "record_event")
        send_email = mocker.patch.object(
            views, "send_primary_email_change_email", autospec=True
        )

        view = views.ManageVerifiedAccountViews(post_request)
        result = view.change_primary_email()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == post_request.path
        send_email.assert_not_called()
        post_request.session.flash.assert_called_once_with(
            f"Email address {new_primary.email} set as primary", queue="success"
        )
        assert new_primary.primary
        record_event.assert_called_once_with(
            tag=EventTag.Account.EmailPrimaryChange,
            request=post_request,
            additional={"old_primary": None, "new_primary": new_primary.email},
        )

    @pytest.mark.parametrize("email_id", ["9999", "999999999999", "nope"])
    def test_change_primary_email_not_found(
        self, post_request, default_response, email_id
    ):
        user = UserFactory.create()
        old_primary = EmailFactory.create(primary=True, user=user)
        post_request.user = user
        post_request.POST = MultiDict({"primary_email_id": email_id})

        view = views.ManageVerifiedAccountViews(post_request)

        assert view.change_primary_email() == default_response
        post_request.session.flash.assert_called_once_with(
            "Email address not found", queue="error"
        )
        assert old_primary.primary

    def test_change_primary_email_2fa_disabled(self, post_request, default_response):
        user = UserFactory.create(totp_secret=None)
        primary = EmailFactory.create(primary=True, verified=False, user=user)
        secondary = EmailFactory.create(primary=False, verified=True, user=user)
        post_request.user = user
        post_request.POST = MultiDict({"primary_email_id": str(secondary.id)})

        view = views.ManageVerifiedAccountViews(post_request)

        assert view.change_primary_email() == default_response
        post_request.session.flash.assert_called_once_with(
            "Two factor authentication must be enabled to change primary "
            "email address.",
            queue="error",
        )
        assert primary.primary
        assert not secondary.primary

    @pytest.mark.parametrize(
        ("has_primary_verified_email", "expected_redirect"),
        [
            (True, "manage.account"),
            (False, "manage.unverified-account"),
        ],
    )
    def test_reverify_email(
        self,
        post_request,
        limiters,
        mocker,
        has_primary_verified_email,
        expected_redirect,
    ):
        user = UserFactory.create()
        if has_primary_verified_email:
            EmailFactory.create(user=user, primary=True, verified=True)
        email = EmailFactory.create(
            user=user, primary=False, verified=False, email="email_address"
        )
        post_request.user = user
        post_request.POST = MultiDict({"reverify_email_id": str(email.id)})
        record_event = mocker.spy(user, "record_event")
        send_email = mocker.patch.object(
            views, "send_email_verification_email", autospec=True
        )

        view = views.ManageVerifiedAccountViews(post_request)
        result = view.reverify_email()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == f"/{expected_redirect}/"
        post_request.session.flash.assert_called_once_with(
            "Verification email for email_address resent", queue="success"
        )
        send_email.assert_called_once_with(post_request, (user, email))
        limiters["email.verify"].test.assert_called_once_with(user.id)
        limiters["email.verify"].hit.assert_called_once_with(user.id)
        record_event.assert_called_once_with(
            tag=EventTag.Account.EmailReverify,
            request=post_request,
            additional={"email": email.email},
        )
        post_request.route_path.assert_called_once_with(expected_redirect)

    def test_reverify_email_ratelimit_exceeded(
        self, verified_request, limiters, mocker
    ):
        user = verified_request.user
        email = EmailFactory.create(user=user, primary=False, verified=False)
        verified_request.POST = MultiDict({"reverify_email_id": str(email.id)})
        limiters["email.verify"].test.return_value = False
        record_event = mocker.spy(user, "record_event")
        send_email = mocker.patch.object(
            views, "send_email_verification_email", autospec=True
        )

        view = views.ManageVerifiedAccountViews(verified_request)
        result = view.reverify_email()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account/"
        verified_request.session.flash.assert_called_once_with(
            (
                "Too many incomplete attempts to verify email address(es) for "
                f"{user.username}. Complete a pending "
                "verification or wait before attempting again."
            ),
            queue="error",
        )
        limiters["email.verify"].test.assert_called_once_with(user.id)
        limiters["email.verify"].hit.assert_not_called()
        send_email.assert_not_called()
        record_event.assert_not_called()

    @pytest.mark.parametrize("reverify_email_id", ["9999", "999999999999", "wutang"])
    @pytest.mark.parametrize(
        ("has_primary_verified_email", "expected"),
        [
            (True, "manage.account"),
            (False, "manage.unverified-account"),
        ],
    )
    def test_reverify_email_not_found(
        self,
        post_request,
        mocker,
        reverify_email_id,
        has_primary_verified_email,
        expected,
    ):
        user = UserFactory.create()
        EmailFactory.create(user=user, verified=has_primary_verified_email)
        post_request.user = user
        post_request.POST = MultiDict({"reverify_email_id": reverify_email_id})
        send_email = mocker.patch.object(
            views, "send_email_verification_email", autospec=True
        )

        view = views.ManageVerifiedAccountViews(post_request)
        result = view.reverify_email()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == f"/{expected}/"
        post_request.session.flash.assert_called_once_with(
            "Email address not found", queue="error"
        )
        send_email.assert_not_called()
        post_request.route_path.assert_called_once_with(expected)

    def test_reverify_email_already_verified(self, verified_request, limiters, mocker):
        email = verified_request.user.primary_email
        verified_request.POST = MultiDict({"reverify_email_id": str(email.id)})
        send_email = mocker.patch.object(
            views, "send_email_verification_email", autospec=True
        )

        view = views.ManageVerifiedAccountViews(verified_request)
        result = view.reverify_email()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account/"
        verified_request.session.flash.assert_called_once_with(
            "Email is already verified", queue="error"
        )
        send_email.assert_not_called()
        limiters["email.verify"].test.assert_not_called()

    def test_change_password(
        self, real_session_request, user_password, user_service, mocker
    ):
        new_password = "mysupersecurepassword1!"
        user = real_session_request.user
        real_session_request.POST = MultiDict(
            {
                "password": user_password,
                "new_password": new_password,
                "password_confirm": new_password,
            }
        )
        update_user = mocker.spy(user_service, "update_user")
        record_event = mocker.spy(user, "record_event")
        send_email = mocker.patch.object(
            views, "send_password_change_email", autospec=True
        )

        view = views.ManageVerifiedAccountViews(real_session_request)
        result = view.change_password()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == real_session_request.path
        real_session_request.session.flash.assert_called_once_with(
            "Password updated", queue="success"
        )
        send_email.assert_called_once_with(real_session_request, user)
        update_user.assert_called_once_with(user.id, password=new_password)
        assert user_service.check_password(user.id, new_password)
        record_event.assert_called_once_with(
            tag=EventTag.Account.PasswordChange,
            request=real_session_request,
        )
        assert (
            real_session_request.session[Session._password_timestamp_key]
            == user.password_date.timestamp()
        )

    def test_change_password_validation_fails(
        self, verified_request, user_password, user_service, mocker, default_response
    ):
        new_password = "mysupersecurepassword1!"
        verified_request.POST = MultiDict(
            {
                "password": user_password,
                "new_password": new_password,
                "password_confirm": "something else",
            }
        )
        update_user = mocker.spy(user_service, "update_user")
        send_email = mocker.patch.object(
            views, "send_password_change_email", autospec=True
        )

        view = views.ManageVerifiedAccountViews(verified_request)
        result = view.change_password()

        form = result["change_password_form"]
        assert result == {**default_response, "change_password_form": form}
        assert isinstance(form, views.ChangePasswordForm)
        assert form.password_confirm.errors
        verified_request.session.flash.assert_not_called()
        send_email.assert_not_called()
        update_user.assert_not_called()

    def test_delete_account(self, verified_request, user_password, mocker):
        user = verified_request.user
        deleted_user = UserFactory.create(username="deleted-user")
        jid = JournalEntryFactory.create(submitted_by=user).id
        verified_request.params = {"confirm_password": user_password}
        send_email = mocker.patch.object(
            views, "send_account_deletion_email", autospec=True
        )
        logout = mocker.patch.object(
            views,
            "logout",
            autospec=True,
            return_value=mocker.sentinel.logout_response,
        )

        view = views.ManageVerifiedAccountViews(verified_request)

        assert view.delete_account() is mocker.sentinel.logout_response

        journal = (
            verified_request.db.scalars(
                select(JournalEntry)
                .options(joinedload(JournalEntry.submitted_by))
                .where(JournalEntry.id == jid)
            )
            .unique()
            .one()
        )

        assert journal.submitted_by == deleted_user
        assert verified_request.db.scalars(select(User)).unique().all() == [
            deleted_user
        ]
        send_email.assert_called_once_with(verified_request, user)
        logout.assert_called_once_with(verified_request)

    def test_delete_account_no_confirm(self, verified_request, default_response):
        verified_request.params = {"confirm_password": ""}

        view = views.ManageVerifiedAccountViews(verified_request)

        assert view.delete_account() == default_response
        verified_request.session.flash.assert_called_once_with(
            "Confirm the request", queue="error"
        )

    @pytest.mark.usefixtures("user_password")
    def test_delete_account_wrong_confirm(self, verified_request, default_response):
        verified_request.params = {"confirm_password": "invalid"}

        view = views.ManageVerifiedAccountViews(verified_request)

        assert view.delete_account() == default_response
        verified_request.session.flash.assert_called_once_with(
            "Could not delete account - Invalid credentials. Please try again.",
            queue="error",
        )

    def test_delete_account_has_active_projects(
        self, verified_request, user_password, default_response
    ):
        verified_request.params = {"confirm_password": user_password}
        RoleFactory.create(user=verified_request.user, role_name="Owner")

        view = views.ManageVerifiedAccountViews(verified_request)

        assert view.delete_account() == default_response
        verified_request.session.flash.assert_called_once_with(
            "Cannot delete account with active project ownerships", queue="error"
        )

    @pytest.mark.parametrize(
        "orgtype", [OrganizationType.Community, OrganizationType.Company]
    )
    def test_delete_account_has_sole_organizations(
        self, verified_request, user_password, default_response, orgtype
    ):
        """
        A sole organization ownership blocks deletion even without a sole
        project ownership. A Company org with no subscription is not in good
        standing, but its owner can still reach the settings page to delete it
        or hand it off, so it blocks too.
        """
        verified_request.params = {"confirm_password": user_password}
        OrganizationRoleFactory.create(
            organization=OrganizationFactory.create(orgtype=orgtype),
            user=verified_request.user,
            role_name=OrganizationRoleType.Owner,
        )

        view = views.ManageVerifiedAccountViews(verified_request)

        assert view.delete_account() == default_response
        verified_request.session.flash.assert_called_once_with(
            "Cannot delete account with sole organization ownerships", queue="error"
        )


class Test2FA:
    def test_manage_two_factor(self, mocker):
        assert views.manage_two_factor(mocker.sentinel.request) == {}


class TestProvisionTOTP:
    def test_generate_totp_qr(self, two_factor_request):
        session = two_factor_request.session

        view = views.ProvisionTOTPViews(two_factor_request)
        result = view.generate_totp_qr()

        assert isinstance(result, HTTPOk)
        assert result.content_type == "image/svg+xml"
        assert b"<svg" in result.body
        assert session.totp_secret_status() == "present"
        session.flash.assert_not_called()

    def test_generate_totp_qr_two_factor_not_allowed(self, post_request):
        post_request.user = UserFactory.create()

        view = views.ProvisionTOTPViews(post_request)
        result = view.generate_totp_qr()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account/"
        post_request.session.flash.assert_called_once_with(
            "Verify your email to modify two factor authentication", queue="error"
        )

    def test_totp_provision(self, two_factor_request):
        user = two_factor_request.user
        secret = two_factor_request.session.get_totp_secret()

        view = views.ProvisionTOTPViews(two_factor_request)
        result = view.totp_provision()

        form = result["provision_totp_form"]
        assert result == {
            "provision_totp_secret": base64.b32encode(secret).decode(),
            "provision_totp_form": form,
            "provision_totp_uri": otp.generate_totp_provisioning_uri(
                secret, user.username, issuer_name="PyPI"
            ),
        }
        assert isinstance(form, views.ProvisionTOTPForm)
        assert form.totp_secret == secret

    @pytest.mark.parametrize(
        ("burned", "verified", "expected_route", "expected_flash"),
        [
            (False, True, "manage.account.recovery-codes.burn", None),
            (
                True,
                False,
                "manage.account",
                "Verify your email to modify two factor authentication",
            ),
        ],
    )
    def test_totp_provision_two_factor_not_allowed(
        self, post_request, burned, verified, expected_route, expected_flash
    ):
        user = UserFactory.create(with_verified_primary_email=verified)
        if burned:
            RecoveryCodeFactory.create(user=user, burned=dt.datetime.now(dt.UTC))
        post_request.user = user

        view = views.ProvisionTOTPViews(post_request)
        result = view.totp_provision()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == f"/{expected_route}/"
        if expected_flash is None:
            post_request.session.flash.assert_not_called()
        else:
            post_request.session.flash.assert_called_once_with(
                expected_flash, queue="error"
            )

    @pytest.mark.parametrize("current_totp_secret", [b"foobar", None])
    def test_validate_totp_provision(
        self, two_factor_request, user_service, metrics, mocker, current_totp_secret
    ):
        user = two_factor_request.user
        user.totp_secret = current_totp_secret
        session = two_factor_request.session
        secret = session.get_totp_secret()
        two_factor_request.POST = MultiDict(
            {"totp_value": otp._get_totp(secret).generate(time.time()).decode()}
        )
        get_totp_secret = mocker.spy(session, "get_totp_secret")
        update_user = mocker.spy(user_service, "update_user")
        record_event = mocker.spy(user, "record_event")
        send_email = mocker.patch.object(
            views, "send_two_factor_added_email", autospec=True
        )

        view = views.ProvisionTOTPViews(two_factor_request)
        result = view.validate_totp_provision()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account/"
        update_user.assert_called_once_with(user.id, totp_secret=secret)
        assert user.totp_secret == secret
        # A second read could regenerate an expired secret and save the wrong one
        get_totp_secret.assert_called_once_with()
        assert session.totp_secret_status() == "missing"
        session.flash.assert_called_once_with(
            "Authentication application successfully set up", queue="success"
        )
        expected_record_event_calls = [
            mocker.call(
                tag=EventTag.Account.TwoFactorMethodAdded,
                request=two_factor_request,
                additional={"method": "totp"},
            )
        ]
        if current_totp_secret:
            expected_record_event_calls.insert(
                0,
                mocker.call(
                    tag=EventTag.Account.TwoFactorMethodRemoved,
                    request=two_factor_request,
                    additional={"method": "totp"},
                ),
            )
        assert record_event.call_args_list == expected_record_event_calls
        send_email.assert_called_once_with(two_factor_request, user, method="totp")
        metrics.increment.assert_called_once_with(
            "warehouse.manage.account.totp_provision",
            tags=["result:success", "session_secret:present"],
        )

    @pytest.mark.parametrize(
        ("totp_failure", "expected_result", "expected_errors"),
        [
            ("invalid", "invalid", ["Invalid TOTP code. Try again?"]),
            (
                "out_of_sync",
                "out_of_sync",
                ["Invalid TOTP code. Your device time may be out of sync."],
            ),
            (
                "malformed",
                "malformed",
                ["TOTP code must be 6 digits.", "Invalid TOTP code. Try again?"],
            ),
            # Validation stopped before the code was checked, e.g. empty input.
            (None, "malformed", ["This field is required."]),
        ],
    )
    @pytest.mark.parametrize("session_secret", ["present", "missing", "expired"])
    def test_validate_totp_provision_invalid_form(
        self,
        two_factor_request,
        user_service,
        metrics,
        mocker,
        totp_failure,
        expected_result,
        expected_errors,
        session_secret,
    ):
        """
        ``generate_totp_secret`` is pinned so a missing or expired session
        secret regenerates to a known one the submitted codes are built from.
        """
        user = two_factor_request.user
        totp_secret = user.totp_secret
        secret = otp.generate_totp_secret()
        mocker.patch.object(
            otp, "generate_totp_secret", autospec=True, return_value=secret
        )
        session = two_factor_request.session
        if session_secret != "missing":
            session.get_totp_secret()
        if session_secret == "expired":
            session[Session._totp_secret_timestamp_key] -= Session._totp_secret_max_age
        totp = otp._get_totp(secret)
        two_factor_request.POST = MultiDict(
            {
                "totp_value": {
                    "invalid": totp.generate(time.time() + 20 * otp.TOTP_INTERVAL),
                    "out_of_sync": totp.generate(time.time() + 5 * otp.TOTP_INTERVAL),
                    "malformed": b"12345",
                    None: b"",
                }[totp_failure].decode()
            }
        )
        update_user = mocker.spy(user_service, "update_user")

        view = views.ProvisionTOTPViews(two_factor_request)
        result = view.validate_totp_provision()

        two_factor_request.session.flash.assert_not_called()
        update_user.assert_not_called()
        assert user.totp_secret == totp_secret
        metrics.increment.assert_called_once_with(
            "warehouse.manage.account.totp_provision",
            tags=[
                f"result:{expected_result}",
                f"session_secret:{session_secret}",
            ],
        )
        form = result["provision_totp_form"]
        assert isinstance(form, views.ProvisionTOTPForm)
        assert form.totp_secret == secret
        assert form.totp_failure == totp_failure
        assert [str(error) for error in form.totp_value.errors] == (
            expected_errors
            if session_secret == "present"
            else [
                (
                    "Your setup code is no longer valid. "
                    "Scan the new QR code and enter the code it generates."
                )
            ]
        )
        assert result == {
            "provision_totp_secret": base64.b32encode(secret).decode(),
            "provision_totp_form": form,
            "provision_totp_uri": otp.generate_totp_provisioning_uri(
                secret, user.username, issuer_name="PyPI"
            ),
        }

    def test_validate_totp_provision_two_factor_not_allowed(self, post_request):
        user = UserFactory.create()
        RecoveryCodeFactory.create(user=user, burned=dt.datetime.now(dt.UTC))
        post_request.user = user

        view = views.ProvisionTOTPViews(post_request)
        result = view.validate_totp_provision()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account/"
        post_request.session.flash.assert_called_once_with(
            "Verify your email to modify two factor authentication", queue="error"
        )

    def test_validate_totp_provision_without_burned_recovery_codes(
        self, verified_request
    ):
        """Enrolling TOTP requires recovery codes to be confirmed first."""
        user = verified_request.user
        totp_secret = user.totp_secret
        verified_request.POST = MultiDict({"totp_value": "123456"})

        result = views.ProvisionTOTPViews(verified_request).validate_totp_provision()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account.recovery-codes.burn/"
        assert user.totp_secret == totp_secret

    def test_delete_totp(self, two_factor_request, user_password, user_service, mocker):
        user = two_factor_request.user
        WebAuthnFactory.create(user=user)
        two_factor_request.POST = MultiDict({"confirm_password": user_password})
        update_user = mocker.spy(user_service, "update_user")
        record_event = mocker.spy(user, "record_event")
        send_email = mocker.patch.object(
            views, "send_two_factor_removed_email", autospec=True
        )

        view = views.ProvisionTOTPViews(two_factor_request)
        result = view.delete_totp()

        update_user.assert_called_once_with(user.id, totp_secret=None)
        assert user.totp_secret is None
        two_factor_request.session.flash.assert_called_once_with(
            "Authentication application removed from PyPI. "
            "Remember to remove PyPI from your application.",
            queue="success",
        )
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account/"
        record_event.assert_called_once_with(
            tag=EventTag.Account.TwoFactorMethodRemoved,
            request=two_factor_request,
            additional={"method": "totp"},
        )
        send_email.assert_called_once_with(two_factor_request, user, method="totp")

    @pytest.mark.usefixtures("user_password")
    def test_delete_totp_bad_password(self, two_factor_request, user_service, mocker):
        user = two_factor_request.user
        totp_secret = user.totp_secret
        WebAuthnFactory.create(user=user)
        two_factor_request.POST = MultiDict({"confirm_password": "wrong password"})
        update_user = mocker.spy(user_service, "update_user")
        send_email = mocker.patch.object(
            views, "send_two_factor_removed_email", autospec=True
        )

        view = views.ProvisionTOTPViews(two_factor_request)
        result = view.delete_totp()

        update_user.assert_not_called()
        assert user.totp_secret == totp_secret
        send_email.assert_not_called()
        two_factor_request.session.flash.assert_called_once_with(
            "Invalid credentials. Try again", queue="error"
        )
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account/"

    def test_delete_totp_not_provisioned(
        self, two_factor_request, user_service, mocker
    ):
        two_factor_request.user.totp_secret = None
        two_factor_request.POST = MultiDict({"confirm_password": "password"})
        update_user = mocker.spy(user_service, "update_user")

        view = views.ProvisionTOTPViews(two_factor_request)
        result = view.delete_totp()

        update_user.assert_not_called()
        two_factor_request.session.flash.assert_called_once_with(
            "There is no authentication application to delete", queue="error"
        )
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account/"

    def test_delete_totp_two_factor_not_allowed(self, post_request):
        post_request.user = UserFactory.create()

        view = views.ProvisionTOTPViews(post_request)
        result = view.delete_totp()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account/"
        post_request.session.flash.assert_called_once_with(
            "Verify your email to modify two factor authentication", queue="error"
        )

    def test_delete_totp_last_2fa(self, two_factor_request, user_service, mocker):
        user = two_factor_request.user
        totp_secret = user.totp_secret
        two_factor_request.POST = MultiDict({"confirm_password": "password"})
        update_user = mocker.spy(user_service, "update_user")

        view = views.ProvisionTOTPViews(two_factor_request)
        result = view.delete_totp()

        update_user.assert_not_called()
        assert user.totp_secret == totp_secret
        two_factor_request.session.flash.assert_called_once_with(
            "Cannot remove last 2FA method", queue="error"
        )
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account/"


class TestProvisionWebAuthn:
    def test_get_webauthn_view(self, two_factor_request):
        view = views.ProvisionWebAuthnViews(two_factor_request)
        result = view.webauthn_provision()

        assert result == {}

    def test_get_webauthn_view_redirect(self, verified_request):
        view = views.ProvisionWebAuthnViews(verified_request)
        result = view.webauthn_provision()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account.recovery-codes.burn/"

    def test_get_webauthn_options(self, two_factor_request, user_service, mocker):
        get_options = mocker.spy(user_service, "get_webauthn_credential_options")
        challenge = two_factor_request.session.get_webauthn_challenge()

        view = views.ProvisionWebAuthnViews(two_factor_request)
        result = view.webauthn_provision_options()

        assert result == get_options.spy_return
        get_options.assert_called_once_with(
            two_factor_request.user.id,
            challenge=challenge,
            rp_name="PyPI",
            rp_id=two_factor_request.domain,
        )
        assert result["rp"] == {"id": two_factor_request.domain, "name": "PyPI"}
        assert result["challenge"] == bytes_to_base64url(challenge)

    def test_validate_webauthn_provision(
        self, two_factor_request, user_service, mocker
    ):
        """
        Registration verification needs a real browser credential, so the
        ``warehouse.utils.webauthn`` boundary is patched; the service's
        credential-in-use check and ``add_webauthn`` still run for real.
        """
        user = two_factor_request.user
        session = two_factor_request.session
        two_factor_request.POST = MultiDict({"label": "fake_label", "credential": "{}"})
        verify = mocker.patch(
            "warehouse.utils.webauthn.verify_registration_response",
            autospec=True,
            return_value=VerifiedRegistration(
                credential_id=b"fake_credential_id",
                credential_public_key=b"fake_public_key",
                sign_count=1,
                aaguid="wutang",
                fmt=AttestationFormat.NONE,
                credential_type=PublicKeyCredentialType.PUBLIC_KEY,
                user_verified=False,
                attestation_object=b"foobar",
                credential_device_type="single_device",
                credential_backed_up=False,
            ),
        )
        get_challenge = mocker.spy(session, "get_webauthn_challenge")
        clear_challenge = mocker.spy(session, "clear_webauthn_challenge")
        add_webauthn = mocker.spy(user_service, "add_webauthn")
        record_event = mocker.spy(user, "record_event")
        send_email = mocker.patch.object(
            views, "send_two_factor_added_email", autospec=True
        )

        view = views.ProvisionWebAuthnViews(two_factor_request)
        result = view.validate_webauthn_provision()

        get_challenge.assert_called_once_with()
        clear_challenge.assert_called_once_with()
        verify.assert_called_once_with(
            b"{}",
            challenge=get_challenge.spy_return,
            rp_id=two_factor_request.domain,
            origin=two_factor_request.host_url,
        )
        add_webauthn.assert_called_once_with(
            user.id,
            label="fake_label",
            credential_id=bytes_to_base64url(b"fake_credential_id"),
            public_key=bytes_to_base64url(b"fake_public_key"),
            sign_count=1,
        )
        [webauthn] = user.webauthn
        assert webauthn.label == "fake_label"
        assert webauthn.credential_id == bytes_to_base64url(b"fake_credential_id")
        assert webauthn.public_key == bytes_to_base64url(b"fake_public_key")
        assert webauthn.sign_count == 1
        session.flash.assert_called_once_with(
            "Security device successfully set up", queue="success"
        )
        assert result == {"success": "Security device successfully set up"}
        record_event.assert_called_once_with(
            tag=EventTag.Account.TwoFactorMethodAdded,
            request=two_factor_request,
            additional={"method": "webauthn", "label": "fake_label"},
        )
        send_email.assert_called_once_with(two_factor_request, user, method="webauthn")

    def test_validate_webauthn_provision_invalid_form(
        self, two_factor_request, user_service, mocker
    ):
        session = two_factor_request.session
        two_factor_request.POST = MultiDict(
            {"label": "fake_label", "credential": "not json"}
        )
        get_challenge = mocker.spy(session, "get_webauthn_challenge")
        clear_challenge = mocker.spy(session, "clear_webauthn_challenge")
        add_webauthn = mocker.spy(user_service, "add_webauthn")

        view = views.ProvisionWebAuthnViews(two_factor_request)
        result = view.validate_webauthn_provision()

        get_challenge.assert_called_once_with()
        clear_challenge.assert_called_once_with()
        add_webauthn.assert_not_called()
        assert two_factor_request.user.webauthn == []
        session.flash.assert_not_called()
        assert result == {
            "fail": {"errors": ["Invalid WebAuthn credential: Bad payload"]}
        }

    def test_validate_webauthn_provision_without_burned_recovery_codes(
        self, verified_request, mocker
    ):
        """Enrolling a security device requires recovery codes to be confirmed first."""
        user = verified_request.user
        record_event = mocker.spy(user, "record_event")

        view = views.ProvisionWebAuthnViews(verified_request)
        result = view.validate_webauthn_provision()

        assert result == {
            "fail": {
                "errors": [
                    "Confirm your recovery codes before adding a security device"
                ]
            }
        }
        assert user.webauthn == []
        verified_request.session.flash.assert_not_called()
        record_event.assert_not_called()

    def test_delete_webauthn(self, verified_request, mocker):
        """``UserFactory`` sets a TOTP secret, so one key is not the last 2FA."""
        user = verified_request.user
        webauthn = WebAuthnFactory.create(user=user, label="fake label")
        verified_request.POST = MultiDict({"label": "fake label"})
        record_event = mocker.spy(user, "record_event")
        send_email = mocker.patch.object(
            views, "send_two_factor_removed_email", autospec=True
        )

        view = views.ProvisionWebAuthnViews(verified_request)
        result = view.delete_webauthn()

        verified_request.session.flash.assert_called_once_with(
            "Security device removed", queue="success"
        )
        verified_request.route_path.assert_called_once_with("manage.account")
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account/"
        assert user.webauthn == []
        verified_request.db.flush()
        assert verified_request.db.get(WebAuthn, webauthn.id) is None
        record_event.assert_called_once_with(
            tag=EventTag.Account.TwoFactorMethodRemoved,
            request=verified_request,
            additional={"method": "webauthn", "label": "fake label"},
        )
        send_email.assert_called_once_with(verified_request, user, method="webauthn")

    def test_delete_webauthn_not_provisioned(self, verified_request):
        view = views.ProvisionWebAuthnViews(verified_request)
        result = view.delete_webauthn()

        verified_request.session.flash.assert_called_once_with(
            "There is no security device to delete", queue="error"
        )
        verified_request.route_path.assert_called_once_with("manage.account")
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account/"

    def test_delete_webauthn_invalid_form(self, verified_request, mocker):
        user = verified_request.user
        webauthn = WebAuthnFactory.create(user=user, label="fake label")
        verified_request.POST = MultiDict({"label": "other label"})
        record_event = mocker.spy(user, "record_event")
        send_email = mocker.patch.object(
            views, "send_two_factor_removed_email", autospec=True
        )

        view = views.ProvisionWebAuthnViews(verified_request)
        result = view.delete_webauthn()

        verified_request.session.flash.assert_called_once_with(
            "Invalid credentials", queue="error"
        )
        verified_request.route_path.assert_called_once_with("manage.account")
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account/"
        assert user.webauthn == [webauthn]
        record_event.assert_not_called()
        send_email.assert_not_called()

    def test_delete_webauthn_last_2fa(self, verified_request, mocker):
        user = verified_request.user
        user.totp_secret = None
        webauthn = WebAuthnFactory.create(user=user)
        verified_request.POST = MultiDict({"label": webauthn.label})
        record_event = mocker.spy(user, "record_event")
        send_email = mocker.patch.object(
            views, "send_two_factor_removed_email", autospec=True
        )

        view = views.ProvisionWebAuthnViews(verified_request)
        result = view.delete_webauthn()

        verified_request.session.flash.assert_called_once_with(
            "Cannot remove last 2FA method", queue="error"
        )
        verified_request.route_path.assert_called_once_with("manage.account")
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account/"
        assert user.webauthn == [webauthn]
        record_event.assert_not_called()
        send_email.assert_not_called()


@pytest.mark.parametrize(
    "view_class", [views.ProvisionTOTPViews, views.ProvisionWebAuthnViews]
)
def test_two_factor_provisioning_views_require_reauth(app_config, view_class):
    """Adding or removing a 2FA method requires a recent password confirmation."""
    class_views = [
        intr["introspectable"]
        for intr in app_config.registry.introspector.get_category("views")
        if intr["introspectable"]["callable"] is view_class
    ]

    assert class_views
    assert all(view.get("require_reauth") is True for view in class_views)


class TestProvisionRecoveryCodes:
    def test_recovery_codes_generate(self, verified_request, user_service, mocker):
        user = verified_request.user
        generate = mocker.spy(user_service, "generate_recovery_codes")
        record_event = mocker.spy(user, "record_event")
        send_email = mocker.patch.object(
            views, "send_recovery_codes_generated_email", autospec=True
        )

        view = views.ProvisionRecoveryCodesViews(verified_request)
        result = view.recovery_codes_generate()

        generate.assert_called_once_with(user.id)
        assert result == {"recovery_codes": generate.spy_return}
        assert len(result["recovery_codes"]) == RECOVERY_CODE_COUNT
        assert all(
            len(code) == 2 * RECOVERY_CODE_BYTES for code in result["recovery_codes"]
        )
        assert user.recovery_codes.count() == RECOVERY_CODE_COUNT
        record_event.assert_called_once_with(
            tag=EventTag.Account.RecoveryCodesGenerated,
            request=verified_request,
        )
        send_email.assert_called_once_with(verified_request, user)

    def test_recovery_codes_generate_already_exist(
        self, verified_request, user_service, mocker
    ):
        user = verified_request.user
        RecoveryCodeFactory.create(user=user)
        generate = mocker.spy(user_service, "generate_recovery_codes")
        send_email = mocker.patch.object(
            views, "send_recovery_codes_generated_email", autospec=True
        )

        view = views.ProvisionRecoveryCodesViews(verified_request)
        result = view.recovery_codes_generate()

        assert result == {
            "recovery_codes": None,
            "_error": "Recovery codes already generated",
            "_message": (
                "Generating new recovery codes will invalidate your existing codes."
            ),
        }
        generate.assert_not_called()
        send_email.assert_not_called()
        assert user.recovery_codes.count() == 1

    def test_recovery_codes_regenerate(self, verified_request, user_service, mocker):
        user = verified_request.user
        old_code = RecoveryCodeFactory.create(user=user)
        generate = mocker.spy(user_service, "generate_recovery_codes")
        record_event = mocker.spy(user, "record_event")
        send_email = mocker.patch.object(
            views, "send_recovery_codes_generated_email", autospec=True
        )

        view = views.ProvisionRecoveryCodesViews(verified_request)
        result = view.recovery_codes_regenerate()

        generate.assert_called_once_with(user.id)
        assert result == {"recovery_codes": generate.spy_return}
        assert len(result["recovery_codes"]) == RECOVERY_CODE_COUNT
        codes = user.recovery_codes.all()
        assert len(codes) == RECOVERY_CODE_COUNT
        assert old_code.code not in {code.code for code in codes}
        record_event.assert_called_once_with(
            tag=EventTag.Account.RecoveryCodesRegenerated,
            request=verified_request,
        )
        send_email.assert_called_once_with(verified_request, user)

    def test_recovery_codes_burn_get(self, verified_request):
        RecoveryCodeFactory.create(user=verified_request.user)
        verified_request.method = "GET"

        view = views.ProvisionRecoveryCodesViews(verified_request)
        result = view.recovery_codes_burn()

        assert list(result) == ["form"]
        assert isinstance(result["form"], RecoveryCodeAuthenticationForm)
        verified_request.session.flash.assert_not_called()

    def test_recovery_codes_burn_post(self, verified_request, user_service, mocker):
        user = verified_request.user
        codes = user_service.generate_recovery_codes(user.id)
        verified_request.POST = MultiDict({"recovery_code_value": codes[0]})
        send_email = mocker.patch(
            "warehouse.accounts.forms.send_recovery_code_used_email", autospec=True
        )

        view = views.ProvisionRecoveryCodesViews(verified_request)
        result = view.recovery_codes_burn()

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage.account.two-factor/"
        verified_request.route_path.assert_called_once_with("manage.account.two-factor")
        verified_request.session.flash.assert_called_once_with(
            "Recovery code accepted. The supplied code cannot be used again.",
            queue="success",
        )
        assert [code.burned is not None for code in user.recovery_codes].count(
            True
        ) == 1
        send_email.assert_called_once_with(verified_request, user)

    @pytest.mark.parametrize(
        ("has_burned", "expected"),
        [(False, "manage.account"), (True, "manage.account.two-factor")],
    )
    def test_recovery_codes_burn_redirect(self, verified_request, has_burned, expected):
        """
        A user with no recovery codes has nothing to burn; one who already
        burned a code has confirmed them.
        """
        user = verified_request.user
        if has_burned:
            RecoveryCodeFactory.create(user=user)
            RecoveryCodeFactory.create(user=user, burned=dt.datetime.now(dt.UTC))

        view = views.ProvisionRecoveryCodesViews(verified_request)
        result = view.recovery_codes_burn()

        assert isinstance(result, HTTPSeeOther)
        assert result.location == f"/{expected}/"
        verified_request.route_path.assert_called_once_with(expected)


class TestProvisionMacaroonViews:
    @pytest.fixture
    def user_macaroon(self, verified_request):
        """A user-scoped API token owned by the ``verified_request`` user."""
        user = verified_request.user
        return MacaroonFactory.create(
            user_id=user.id,
            description="fake macaroon",
            permissions_caveat={"permissions": "user"},
            caveats=[caveats.RequestUser(user_id=str(user.id))],
        )

    def test_default_response(self, verified_request, macaroon_service, user_service):
        user = verified_request.user
        project = ProjectFactory.create(name="foo")
        RoleFactory.create(user=user, project=project, role_name="Owner")

        view = views.ProvisionMacaroonViews(verified_request)
        result = view.default_response

        assert set(result) == {
            "project_names",
            "create_macaroon_form",
            "delete_macaroon_form",
        }
        assert result["project_names"] == ["foo"]
        create_form = result["create_macaroon_form"]
        assert isinstance(create_form, CreateMacaroonForm)
        assert create_form.user_id == user.id
        assert create_form.macaroon_service is macaroon_service
        assert create_form.project_names == ["foo"]
        assert create_form.token_scope.data is None
        delete_form = result["delete_macaroon_form"]
        assert isinstance(delete_form, DeleteMacaroonForm)
        assert delete_form.request is verified_request
        assert delete_form.username.data == user.username
        assert delete_form.user_service is user_service
        assert delete_form.macaroon_service is macaroon_service

    def test_project_names(self, db_request):
        user = UserFactory.create()
        another_user = UserFactory.create()

        db_request.user = user

        # A project with a sole owner that is the user
        with_sole_owner = ProjectFactory.create(name="foo")
        RoleFactory.create(user=user, project=with_sole_owner, role_name="Owner")
        RoleFactory.create(
            user=another_user, project=with_sole_owner, role_name="Maintainer"
        )

        # A project with multiple owners, including the user
        with_multiple_owners = ProjectFactory.create(name="bar")
        RoleFactory.create(user=user, project=with_multiple_owners, role_name="Owner")
        RoleFactory.create(
            user=another_user, project=with_multiple_owners, role_name="Owner"
        )

        # A project with a sole owner that is not the user
        not_an_owner = ProjectFactory.create(name="baz")
        RoleFactory.create(user=user, project=not_an_owner, role_name="Maintainer")
        RoleFactory.create(user=another_user, project=not_an_owner, role_name="Owner")

        # A project that the user is neither owner nor maintainer of
        neither_owner_nor_maintainer = ProjectFactory.create(name="quux")
        RoleFactory.create(
            user=another_user, project=neither_owner_nor_maintainer, role_name="Owner"
        )

        view = views.ProvisionMacaroonViews(db_request)
        assert set(view.project_names) == {"foo", "bar", "baz"}

    def test_manage_macaroons(self, verified_request):
        project = ProjectFactory.create(name="foo")
        RoleFactory.create(user=verified_request.user, project=project)
        verified_request.method = "GET"
        verified_request.params = {"selected_project": "foo"}

        view = views.ProvisionMacaroonViews(verified_request)
        result = view.manage_macaroons()

        assert result["project_names"] == ["foo"]
        assert isinstance(result["create_macaroon_form"], CreateMacaroonForm)
        assert result["create_macaroon_form"].token_scope.data == "scope:project:foo"
        assert isinstance(result["delete_macaroon_form"], DeleteMacaroonForm)

    def test_create_macaroon_not_allowed(self, post_request, macaroon_service, mocker):
        post_request.user = UserFactory.create()
        create_macaroon = mocker.spy(macaroon_service, "create_macaroon")

        view = views.ProvisionMacaroonViews(post_request)
        result = view.create_macaroon()

        post_request.route_path.assert_called_once_with("manage.account")
        post_request.session.flash.assert_called_once_with(
            "Verify your email to create an API token.", queue="error"
        )
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage.account/"
        create_macaroon.assert_not_called()

    def test_create_macaroon_invalid_form(
        self, verified_request, macaroon_service, mocker
    ):
        create_macaroon = mocker.spy(macaroon_service, "create_macaroon")
        record_event = mocker.spy(verified_request.user, "record_event")

        view = views.ProvisionMacaroonViews(verified_request)
        result = view.create_macaroon()

        assert set(result) == {
            "project_names",
            "create_macaroon_form",
            "delete_macaroon_form",
        }
        form = result["create_macaroon_form"]
        assert isinstance(form, CreateMacaroonForm)
        assert form.errors == {
            "description": ["Specify a token name"],
            "token_scope": ["Specify the token scope"],
        }
        create_macaroon.assert_not_called()
        record_event.assert_not_called()
        assert verified_request.db.scalars(select(Macaroon)).all() == []

    @pytest.mark.parametrize("has_2fa", [True, False])
    def test_create_macaroon(self, verified_request, macaroon_service, mocker, has_2fa):
        user = verified_request.user
        if not has_2fa:
            user.totp_secret = None
        verified_request.POST = MultiDict(
            {"description": "my token", "token_scope": "scope:user"}
        )
        create_macaroon = mocker.spy(macaroon_service, "create_macaroon")
        record_event = mocker.spy(user, "record_event")

        view = views.ProvisionMacaroonViews(verified_request)
        result = view.create_macaroon()

        create_macaroon.assert_called_once_with(
            location=verified_request.domain,
            user_id=user.id,
            description="my token",
            scopes=[caveats.RequestUser(user_id=str(user.id))],
            additional={"made_with_2fa": has_2fa},
        )
        serialized_macaroon, macaroon = create_macaroon.spy_return
        assert set(result) == {
            "project_names",
            "create_macaroon_form",
            "delete_macaroon_form",
            "serialized_macaroon",
            "macaroon",
        }
        assert result["serialized_macaroon"] == serialized_macaroon
        assert result["macaroon"] is macaroon
        assert isinstance(result["create_macaroon_form"], CreateMacaroonForm)
        assert macaroon_service.find_macaroon(str(macaroon.id)) is macaroon
        assert macaroon.user_id == user.id
        assert macaroon.description == "my token"
        assert macaroon.permissions_caveat == {"permissions": "user"}
        assert macaroon.caveats == [caveats.RequestUser(user_id=str(user.id))]
        assert macaroon.additional == {"made_with_2fa": has_2fa}
        record_event.assert_called_once_with(
            tag=EventTag.Account.APITokenAdded,
            request=verified_request,
            additional={
                "description": "my token",
                "caveats": [{"permissions": "user", "version": 1}],
            },
        )

    def test_create_macaroon_records_events_for_each_project(
        self, verified_request, macaroon_service, mocker
    ):
        """
        ``CreateMacaroonForm`` only validates a single-project scope, so the
        token covers ``foo`` and the user's other project ``bar`` must get no
        event and no place in the caveats.
        """
        user = verified_request.user
        user.totp_secret = None
        foo = ProjectFactory.create(name="foo")
        bar = ProjectFactory.create(name="bar")
        RoleFactory.create(user=user, project=foo, role_name="Owner")
        RoleFactory.create(user=user, project=bar, role_name="Owner")
        verified_request.POST = MultiDict(
            {"description": "my token", "token_scope": "scope:project:foo"}
        )
        create_macaroon = mocker.spy(macaroon_service, "create_macaroon")
        record_event = mocker.spy(user, "record_event")
        foo_record_event = mocker.spy(foo, "record_event")
        bar_record_event = mocker.spy(bar, "record_event")

        view = views.ProvisionMacaroonViews(verified_request)
        result = view.create_macaroon()

        create_macaroon.assert_called_once_with(
            location=verified_request.domain,
            user_id=user.id,
            description="my token",
            scopes=[
                caveats.ProjectName(normalized_names=["foo"]),
                caveats.ProjectID(project_ids=[str(foo.id)]),
            ],
            additional={"made_with_2fa": False},
        )
        serialized_macaroon, macaroon = create_macaroon.spy_return
        assert result["serialized_macaroon"] == serialized_macaroon
        assert result["macaroon"] is macaroon
        assert isinstance(result["create_macaroon_form"], CreateMacaroonForm)
        assert macaroon.permissions_caveat == {"permissions": {"projects": ["foo"]}}
        assert macaroon.caveats == [
            caveats.ProjectName(normalized_names=["foo"]),
            caveats.ProjectID(project_ids=[str(foo.id)]),
        ]
        record_event.assert_called_once_with(
            tag=EventTag.Account.APITokenAdded,
            request=verified_request,
            additional={
                "description": "my token",
                "caveats": [
                    {"permissions": {"projects": ["foo"]}, "version": 1},
                    {"project_ids": [str(foo.id)]},
                ],
            },
        )
        foo_record_event.assert_called_once_with(
            tag=EventTag.Project.APITokenAdded,
            request=verified_request,
            additional={"description": "my token", "user": user.username},
        )
        bar_record_event.assert_not_called()

    @pytest.mark.parametrize(
        ("referer", "expected_location"),
        [
            ("/fake/safe/route", "/fake/safe/route"),
            ("http://google.com/", "/manage.account/"),
        ],
    )
    def test_delete_macaroon_invalid_form(
        self,
        verified_request,
        user_password,
        user_macaroon,
        macaroon_service,
        mocker,
        referer,
        expected_location,
    ):
        """An unsafe referer falls back to the account page."""
        verified_request.POST = MultiDict(
            {"confirm_password": "wrong password", "macaroon_id": str(user_macaroon.id)}
        )
        verified_request.referer = referer
        delete_macaroon = mocker.spy(macaroon_service, "delete_macaroon")

        view = views.ProvisionMacaroonViews(verified_request)
        result = view.delete_macaroon()

        if expected_location == referer:
            verified_request.route_path.assert_not_called()
        else:
            verified_request.route_path.assert_called_once_with("manage.account")
        assert isinstance(result, HTTPSeeOther)
        assert result.location == expected_location
        delete_macaroon.assert_not_called()
        assert macaroon_service.find_macaroon(str(user_macaroon.id)) is user_macaroon
        verified_request.session.flash.assert_called_once_with(
            "Invalid credentials. Try again", queue="error"
        )

    def test_delete_macaroon_when_non_existent(
        self, verified_request, macaroon_service, mocker
    ):
        """
        ``DeleteMacaroonForm`` rejects an unknown ``macaroon_id`` itself, so the
        view's own missing-token guard is only reachable if the token vanishes
        between validation and lookup. Patch ``validate`` to get there.
        """
        mocker.patch.object(
            views.DeleteMacaroonForm, "validate", autospec=True, return_value=True
        )
        macaroon_id = str(uuid.uuid4())
        verified_request.POST = MultiDict(
            {"confirm_password": "password", "macaroon_id": macaroon_id}
        )
        find_macaroon = mocker.spy(macaroon_service, "find_macaroon")
        delete_macaroon = mocker.spy(macaroon_service, "delete_macaroon")
        record_event = mocker.spy(verified_request.user, "record_event")

        view = views.ProvisionMacaroonViews(verified_request)
        result = view.delete_macaroon()

        verified_request.route_path.assert_called_once_with("manage.account")
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage.account/"
        find_macaroon.assert_called_once_with(macaroon_id)
        delete_macaroon.assert_not_called()
        record_event.assert_not_called()
        verified_request.session.flash.assert_called_once_with(
            "API Token does not exist.", queue="warning"
        )

    def test_delete_macaroon_not_owned(
        self, verified_request, user_password, macaroon_service, mocker
    ):
        owner = verified_request.user
        other_user = UserFactory.create()
        macaroon = MacaroonFactory.create(
            user_id=other_user.id,
            description="not my token",
            permissions_caveat={"permissions": "user"},
            caveats=[caveats.RequestUser(user_id=str(other_user.id))],
        )
        verified_request.POST = MultiDict(
            {"confirm_password": user_password, "macaroon_id": str(macaroon.id)}
        )
        verified_request.referer = "/fake/safe/route"
        delete_macaroon = mocker.spy(macaroon_service, "delete_macaroon")
        record_event = mocker.spy(owner, "record_event")

        view = views.ProvisionMacaroonViews(verified_request)
        result = view.delete_macaroon()

        assert isinstance(result, HTTPSeeOther)
        verified_request.route_path.assert_called_once_with("manage.account")
        assert result.location == "/manage.account/"
        verified_request.session.flash.assert_called_once_with(
            "API Token does not exist.", queue="warning"
        )
        # Macaroon must still exist (not deleted)
        delete_macaroon.assert_not_called()
        assert macaroon_service.find_macaroon(str(macaroon.id)) == macaroon
        # Must NOT have recorded any events
        record_event.assert_not_called()

    @pytest.mark.parametrize("project_scoped", [False, True])
    def test_delete_macaroon(
        self,
        verified_request,
        user_password,
        user_macaroon,
        macaroon_service,
        mocker,
        project_scoped,
    ):
        """
        A project-scoped token names ``foo``, ``bar`` and ``baz``; the user has
        roles on ``foo`` and ``bar`` only, so ``baz`` must get no event. A
        user-scoped token records no project events.
        """
        user = verified_request.user
        foo = ProjectFactory.create(name="foo")
        bar = ProjectFactory.create(name="bar")
        baz = ProjectFactory.create(name="baz")
        RoleFactory.create(user=user, project=foo, role_name="Owner")
        RoleFactory.create(user=user, project=bar, role_name="Owner")
        if project_scoped:
            user_macaroon.permissions_caveat = {
                "permissions": {"projects": ["foo", "bar", "baz"]}
            }
            user_macaroon.caveats = [
                caveats.ProjectName(normalized_names=["foo", "bar", "baz"]),
                caveats.ProjectID(project_ids=[str(foo.id), str(bar.id), str(baz.id)]),
            ]
        macaroon_id = str(user_macaroon.id)
        verified_request.POST = MultiDict(
            {"confirm_password": user_password, "macaroon_id": macaroon_id}
        )
        verified_request.referer = "/fake/safe/route"
        delete_macaroon = mocker.spy(macaroon_service, "delete_macaroon")
        record_event = mocker.spy(user, "record_event")
        foo_record_event = mocker.spy(foo, "record_event")
        bar_record_event = mocker.spy(bar, "record_event")
        baz_record_event = mocker.spy(baz, "record_event")

        view = views.ProvisionMacaroonViews(verified_request)
        result = view.delete_macaroon()

        verified_request.route_path.assert_not_called()
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/fake/safe/route"
        delete_macaroon.assert_called_once_with(macaroon_id)
        assert macaroon_service.find_macaroon(macaroon_id) is None
        verified_request.session.flash.assert_called_once_with(
            "Deleted API token 'fake macaroon'.", queue="success"
        )
        record_event.assert_called_once_with(
            tag=EventTag.Account.APITokenRemoved,
            request=verified_request,
            additional={"macaroon_id": macaroon_id},
        )
        for project_record_event in (foo_record_event, bar_record_event):
            if project_scoped:
                project_record_event.assert_called_once_with(
                    tag=EventTag.Project.APITokenRemoved,
                    request=verified_request,
                    additional={"description": "fake macaroon", "user": user.username},
                )
            else:
                project_record_event.assert_not_called()
        baz_record_event.assert_not_called()


class TestManageProjects:
    def test_manage_projects(self, db_request):
        older_release = ReleaseFactory(created=dt.datetime(2015, 1, 1))
        project_with_older_release = older_release.project
        newer_release = ReleaseFactory(created=dt.datetime(2017, 1, 1))
        project_with_newer_release = newer_release.project
        older_project_with_no_releases = ProjectFactory(
            releases=[], created=dt.datetime(2016, 1, 1)
        )
        newer_project_with_no_releases = ProjectFactory(
            releases=[], created=dt.datetime(2018, 1, 1)
        )
        team_project = ProjectFactory(
            name="team-proj", releases=[], created=dt.datetime(2022, 3, 3)
        )
        archived_project = ProjectFactory(
            releases=[],
            created=dt.datetime(2019, 1, 1),
            lifecycle_status=LifecycleStatus.Archived,
        )

        db_request.user = UserFactory()
        RoleFactory.create(
            user=db_request.user,
            project=project_with_older_release,
            role_name="Maintainer",
        )
        RoleFactory.create(
            user=db_request.user, project=project_with_newer_release, role_name="Owner"
        )
        RoleFactory.create(
            user=db_request.user,
            project=newer_project_with_no_releases,
            role_name="Owner",
        )
        RoleFactory.create(
            user=db_request.user,
            project=older_project_with_no_releases,
            role_name="Maintainer",
        )
        RoleFactory.create(
            user=db_request.user,
            project=archived_project,
            role_name="Owner",
        )
        user_second_owner = UserFactory()
        RoleFactory.create(
            user=user_second_owner,
            project=project_with_older_release,
            role_name="Owner",
        )
        RoleFactory.create(
            user=user_second_owner,
            project=older_project_with_no_releases,
            role_name="Owner",
        )
        RoleFactory.create(
            user=user_second_owner,
            project=project_with_newer_release,
            role_name="Owner",
        )
        team = TeamFactory()
        TeamRoleFactory.create(team=team, user=db_request.user)
        TeamProjectRoleFactory(
            team=team,
            project=team_project,
            role_name=TeamProjectRoleType.Maintainer,
        )

        assert views.manage_projects(db_request) == {
            "projects_active": [
                team_project,
                newer_project_with_no_releases,
                project_with_newer_release,
                older_project_with_no_releases,
                project_with_older_release,
            ],
            "projects_archived": [
                archived_project,
            ],
            "projects_owned": {
                project_with_newer_release.name,
                newer_project_with_no_releases.name,
                archived_project.name,
            },
            "projects_sole_owned": {
                newer_project_with_no_releases.name,
                archived_project.name,
            },
            "project_invites": [],
        }


class TestManageProjectSettings:
    def test_manage_project_settings(self, monkeypatch):
        request = pretend.stub()
        project = pretend.stub(organization=None, lifecycle_status=None)
        view = views.ManageProjectSettingsViews(project, request)
        form = pretend.stub()
        view.transfer_organization_project_form_class = lambda *a, **kw: form

        user_organizations = pretend.call_recorder(
            lambda *a, **kw: {
                "organizations_managed": [],
                "organizations_owned": [],
                "organizations_billing": [],
            }
        )
        monkeypatch.setattr(views, "user_organizations", user_organizations)

        assert view.manage_project_settings() == {
            "project": project,
            "MAX_FILESIZE": MAX_FILESIZE,
            "MAX_PROJECT_SIZE": MAX_PROJECT_SIZE,
            "transfer_organization_project_form": form,
        }

    def test_manage_project_settings_in_organization_managed(self, monkeypatch):
        request = pretend.stub()
        organization_managed = pretend.stub(name="managed-org", is_active=True)
        organization_owned = pretend.stub(name="owned-org", is_active=True)
        project = pretend.stub(organization=organization_managed, lifecycle_status=None)
        view = views.ManageProjectSettingsViews(project, request)
        form = pretend.stub()
        view.transfer_organization_project_form_class = pretend.call_recorder(
            lambda *a, **kw: form
        )

        user_organizations = pretend.call_recorder(
            lambda *a, **kw: {
                "organizations_managed": [organization_managed],
                "organizations_owned": [organization_owned],
                "organizations_billing": [],
            }
        )
        monkeypatch.setattr(views, "user_organizations", user_organizations)

        assert view.manage_project_settings() == {
            "project": project,
            "MAX_FILESIZE": MAX_FILESIZE,
            "MAX_PROJECT_SIZE": MAX_PROJECT_SIZE,
            "transfer_organization_project_form": form,
        }
        assert view.transfer_organization_project_form_class.calls == [
            pretend.call(organization_choices={organization_owned})
        ]

    def test_manage_project_settings_in_organization_owned(self, monkeypatch):
        request = pretend.stub()
        organization_managed = pretend.stub(name="managed-org", is_active=True)
        organization_owned = pretend.stub(name="owned-org", is_active=True)
        project = pretend.stub(organization=organization_owned, lifecycle_status=None)
        view = views.ManageProjectSettingsViews(project, request)
        form = pretend.stub()
        view.transfer_organization_project_form_class = pretend.call_recorder(
            lambda *a, **kw: form
        )

        user_organizations = pretend.call_recorder(
            lambda *a, **kw: {
                "organizations_managed": [organization_managed],
                "organizations_owned": [organization_owned],
                "organizations_billing": [],
            }
        )
        monkeypatch.setattr(views, "user_organizations", user_organizations)

        assert view.manage_project_settings() == {
            "project": project,
            "MAX_FILESIZE": MAX_FILESIZE,
            "MAX_PROJECT_SIZE": MAX_PROJECT_SIZE,
            "transfer_organization_project_form": form,
        }
        assert view.transfer_organization_project_form_class.calls == [
            pretend.call(organization_choices={organization_managed})
        ]

    def test_remove_organization_project_no_confirm(self):
        user = pretend.stub()
        project = pretend.stub(
            name="foo",
            normalized_name="foo",
            organization=pretend.stub(owners=[user]),
            owners=[user],
        )
        request = pretend.stub(
            POST={},
            user=user,
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        with pytest.raises(HTTPSeeOther) as exc:
            org_views.remove_organization_project(project, request)
        assert exc.value.status_code == 303
        assert exc.value.headers["Location"] == "/foo/bar/"

        assert request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]

    def test_remove_organization_project_wrong_confirm(self):
        user = pretend.stub()
        project = pretend.stub(
            name="foo",
            normalized_name="foo",
            organization=pretend.stub(owners=[user]),
            owners=[user],
        )
        request = pretend.stub(
            POST={"confirm_remove_organization_project_name": "FOO"},
            user=user,
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=pretend.call_recorder(lambda *a, **kw: "/foo/bar/"),
        )

        with pytest.raises(HTTPSeeOther) as exc:
            org_views.remove_organization_project(project, request)
        assert exc.value.status_code == 303
        assert exc.value.headers["Location"] == "/foo/bar/"

        assert request.session.flash.calls == [
            pretend.call(
                (
                    "Could not remove project from organization - "
                    "'FOO' is not the same as 'foo'"
                ),
                queue="error",
            )
        ]

        assert request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]

    def test_remove_organization_project_no_current_organization(
        self, monkeypatch, db_request
    ):
        project = ProjectFactory.create(name="foo")

        db_request.POST = MultiDict(
            {
                "confirm_remove_organization_project_name": project.name,
            }
        )
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        send_organization_project_removed_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_project_removed_email",
            send_organization_project_removed_email,
        )

        result = org_views.remove_organization_project(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                "Could not remove project from organization - no organization found",
                queue="error",
            )
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert send_organization_project_removed_email.calls == []

    def test_remove_organization_project_not_organization_owner(self):
        user = pretend.stub()
        project = pretend.stub(
            name="foo",
            normalized_name="foo",
            organization=pretend.stub(owners=[]),
            owners=[user],
        )
        request = pretend.stub(
            POST={},
            user=user,
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        result = org_views.remove_organization_project(project, request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar/"
        assert request.session.flash.calls == [
            pretend.call(
                (
                    "Could not remove project from organization - "
                    "you do not have the required permissions"
                ),
                queue="error",
            )
        ]

    def test_remove_organization_project_no_individual_owner(
        self, monkeypatch, db_request
    ):
        project = ProjectFactory.create(name="foo")
        OrganizationProjectFactory.create(
            organization=OrganizationFactory.create(name="bar"), project=project
        )

        db_request.POST = MultiDict(
            {
                "confirm_remove_organization_project_name": project.name,
            }
        )
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        OrganizationRoleFactory.create(
            organization=project.organization, user=db_request.user, role_name="Owner"
        )

        result = org_views.remove_organization_project(project, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert db_request.session.flash.calls == [
            pretend.call(
                (
                    "Could not remove project from organization - "
                    "you do not have the required permissions"
                ),
                queue="error",
            )
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]

    def test_remove_organization_project(self, monkeypatch, db_request):
        project = ProjectFactory.create(name="foo")
        organization = OrganizationFactory.create(name="bar")
        OrganizationProjectFactory.create(organization=organization, project=project)

        # Create a team under the departing org with access to the project.
        team = TeamFactory.create(organization=organization)
        TeamProjectRoleFactory.create(team=team, project=project, role_name="Owner")

        db_request.POST = MultiDict(
            {
                "confirm_remove_organization_project_name": project.name,
            }
        )
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        OrganizationRoleFactory.create(
            organization=project.organization, user=db_request.user, role_name="Owner"
        )
        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        send_organization_project_removed_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_project_removed_email",
            send_organization_project_removed_email,
        )

        result = org_views.remove_organization_project(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Removed the project 'foo' from 'bar'", queue="success")
        ]
        assert db_request.route_path.calls == [
            pretend.call(
                "manage.organization.projects",
                organization_name=project.organization.normalized_name,
            )
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert send_organization_project_removed_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=project.organization.name,
                project_name=project.name,
                submitter_username=db_request.user.username,
            ),
        ]

        stale_roles = (
            db_request.db.query(TeamProjectRole)
            .filter(TeamProjectRole.project == project)
            .all()
        )
        assert len(stale_roles) == 0

    def test_transfer_organization_project_no_confirm(self):
        user = pretend.stub()
        project = pretend.stub(
            name="foo",
            normalized_name="foo",
            organization=pretend.stub(owners=[user]),
        )
        request = pretend.stub(
            POST={},
            user=user,
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        with pytest.raises(HTTPSeeOther) as exc:
            org_views.transfer_organization_project(project, request)
        assert exc.value.status_code == 303
        assert exc.value.headers["Location"] == "/foo/bar/"

        assert request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]

    def test_transfer_organization_project_wrong_confirm(self):
        user = pretend.stub()
        project = pretend.stub(
            name="foo",
            normalized_name="foo",
            organization=pretend.stub(owners=[user]),
        )
        request = pretend.stub(
            POST={"confirm_transfer_organization_project_name": "FOO"},
            user=user,
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        with pytest.raises(HTTPSeeOther) as exc:
            org_views.transfer_organization_project(project, request)
        assert exc.value.status_code == 303
        assert exc.value.headers["Location"] == "/foo/bar/"

        assert request.session.flash.calls == [
            pretend.call(
                "Could not transfer project - 'FOO' is not the same as 'foo'",
                queue="error",
            )
        ]

    def test_transfer_organization_project_no_current_organization(
        self, monkeypatch, db_request
    ):
        organization = OrganizationFactory.create(name="baz")
        project = ProjectFactory.create(name="foo")

        db_request.POST = MultiDict(
            {
                "organization": str(organization.id),
                "confirm_transfer_organization_project_name": project.name,
            }
        )
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )
        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        send_organization_project_removed_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_project_removed_email",
            send_organization_project_removed_email,
        )

        send_organization_project_added_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            view_helpers,
            "send_organization_project_added_email",
            send_organization_project_added_email,
        )

        result = org_views.transfer_organization_project(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Transferred the project 'foo' to 'baz'", queue="success")
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert send_organization_project_removed_email.calls == []
        assert send_organization_project_added_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=organization.name,
                project_name=project.name,
                submitter_username=db_request.user.username,
            )
        ]

    def test_transfer_organization_project_not_organization_owner(self):
        user = pretend.stub()
        project = pretend.stub(
            name="foo",
            normalized_name="foo",
            organization=pretend.stub(owners=[]),
        )
        request = pretend.stub(
            POST={},
            user=user,
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        result = org_views.transfer_organization_project(project, request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar/"
        assert request.session.flash.calls == [
            pretend.call(
                (
                    "Could not transfer project - "
                    "you do not have the required permissions"
                ),
                queue="error",
            )
        ]

    def test_transfer_organization_project_no_individual_owner(
        self, monkeypatch, db_request
    ):
        organization = OrganizationFactory.create(name="baz")
        project = ProjectFactory.create(name="foo")
        OrganizationProjectFactory.create(
            organization=OrganizationFactory.create(name="bar"), project=project
        )

        db_request.POST = MultiDict(
            {
                "organization": str(organization.id),
                "confirm_transfer_organization_project_name": project.name,
            }
        )
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )
        OrganizationRoleFactory.create(
            organization=project.organization, user=db_request.user, role_name="Owner"
        )

        send_organization_project_removed_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_project_removed_email",
            send_organization_project_removed_email,
        )

        send_organization_project_added_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            view_helpers,
            "send_organization_project_added_email",
            send_organization_project_added_email,
        )

        result = org_views.transfer_organization_project(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Transferred the project 'foo' to 'baz'", queue="success")
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert send_organization_project_removed_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=project.organization.name,
                project_name=project.name,
                submitter_username=db_request.user.username,
            )
        ]
        assert send_organization_project_added_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=organization.name,
                project_name=project.name,
                submitter_username=db_request.user.username,
            )
        ]

    def test_transfer_organization_project_invalid(self, monkeypatch, db_request):
        project = ProjectFactory.create(name="foo")
        OrganizationProjectFactory.create(
            organization=OrganizationFactory.create(name="bar"), project=project
        )

        db_request.POST = MultiDict(
            {
                "organization": "",
                "confirm_transfer_organization_project_name": project.name,
            }
        )
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        OrganizationRoleFactory.create(
            organization=project.organization, user=db_request.user, role_name="Owner"
        )
        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        result = org_views.transfer_organization_project(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Select organization", queue="error")
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_transfer_organization_project_from_organization_managed(
        self, monkeypatch, db_request
    ):
        organization = OrganizationFactory.create(name="baz")
        organization_managed = OrganizationFactory.create(name="bar-managed")
        organization_owned = OrganizationFactory.create(name="bar-owned")
        project = ProjectFactory.create(name="foo")
        OrganizationProjectFactory.create(
            organization=organization_managed, project=project
        )

        db_request.POST = MultiDict(
            {
                "organization": str(organization.id),
                "confirm_transfer_organization_project_name": project.name,
            }
        )
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )
        OrganizationRoleFactory.create(
            organization=project.organization, user=db_request.user, role_name="Owner"
        )
        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        user_organizations = pretend.call_recorder(
            lambda *a, **kw: {
                "organizations_managed": [organization_managed],
                "organizations_owned": [organization_owned, organization],
                "organizations_billing": [],
            }
        )
        monkeypatch.setattr(org_views, "user_organizations", user_organizations)

        transfer_organization_project_form_class = pretend.call_recorder(
            views.TransferOrganizationProjectForm
        )
        monkeypatch.setattr(
            org_views,
            "TransferOrganizationProjectForm",
            transfer_organization_project_form_class,
        )

        send_organization_project_removed_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_project_removed_email",
            send_organization_project_removed_email,
        )

        send_organization_project_added_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            view_helpers,
            "send_organization_project_added_email",
            send_organization_project_added_email,
        )

        result = org_views.transfer_organization_project(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Transferred the project 'foo' to 'baz'", queue="success")
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]
        assert transfer_organization_project_form_class.calls == [
            pretend.call(
                db_request.POST, organization_choices={organization, organization_owned}
            )
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert send_organization_project_removed_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=project.organization.name,
                project_name=project.name,
                submitter_username=db_request.user.username,
            )
        ]
        assert send_organization_project_added_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=organization.name,
                project_name=project.name,
                submitter_username=db_request.user.username,
            )
        ]

    def test_transfer_organization_project_from_organization_owned(
        self, monkeypatch, db_request
    ):
        organization = OrganizationFactory.create(name="baz")
        organization_managed = OrganizationFactory.create(name="bar-managed")
        organization_owned = OrganizationFactory.create(name="bar-owned")
        project = ProjectFactory.create(name="foo")
        OrganizationProjectFactory.create(
            organization=organization_owned, project=project
        )

        db_request.POST = MultiDict(
            {
                "organization": str(organization.id),
                "confirm_transfer_organization_project_name": project.name,
            }
        )
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )
        OrganizationRoleFactory.create(
            organization=project.organization, user=db_request.user, role_name="Owner"
        )
        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        user_organizations = pretend.call_recorder(
            lambda *a, **kw: {
                "organizations_managed": [organization_managed],
                "organizations_owned": [organization_owned, organization],
                "organizations_billing": [],
            }
        )
        monkeypatch.setattr(org_views, "user_organizations", user_organizations)

        transfer_organization_project_form_class = pretend.call_recorder(
            views.TransferOrganizationProjectForm
        )
        monkeypatch.setattr(
            org_views,
            "TransferOrganizationProjectForm",
            transfer_organization_project_form_class,
        )

        send_organization_project_removed_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            org_views,
            "send_organization_project_removed_email",
            send_organization_project_removed_email,
        )

        send_organization_project_added_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            view_helpers,
            "send_organization_project_added_email",
            send_organization_project_added_email,
        )

        result = org_views.transfer_organization_project(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Transferred the project 'foo' to 'baz'", queue="success")
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]
        assert transfer_organization_project_form_class.calls == [
            pretend.call(
                db_request.POST,
                organization_choices={organization_managed, organization},
            )
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert send_organization_project_removed_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=project.organization.name,
                project_name=project.name,
                submitter_username=db_request.user.username,
            )
        ]
        assert send_organization_project_added_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=organization.name,
                project_name=project.name,
                submitter_username=db_request.user.username,
            )
        ]

    def test_delete_project_no_confirm(self):
        project = pretend.stub(normalized_name="foo")
        request = pretend.stub(
            POST={},
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        with pytest.raises(HTTPSeeOther) as exc:
            views.delete_project(project, request)
        assert exc.value.status_code == 303
        assert exc.value.headers["Location"] == "/foo/bar/"

        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISALLOW_DELETION)
        ]
        assert request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]

    def test_delete_project_wrong_confirm(self):
        project = pretend.stub(name="foo", normalized_name="foo")
        request = pretend.stub(
            POST={"confirm_project_name": "FOO"},
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        with pytest.raises(HTTPSeeOther) as exc:
            views.delete_project(project, request)
        assert exc.value.status_code == 303
        assert exc.value.headers["Location"] == "/foo/bar/"

        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISALLOW_DELETION)
        ]
        assert request.session.flash.calls == [
            pretend.call(
                "Could not delete project - 'FOO' is not the same as 'foo'",
                queue="error",
            )
        ]

    def test_delete_project_no_acknowledgments(self, db_request, mocker):
        """Acknowledgment checkboxes are enforced server-side, not just in the UI."""
        project = ProjectFactory.create(name="foo")
        db_request.user = UserFactory.create()
        db_request.POST["confirm_project_name"] = project.name
        db_request.route_path = mocker.Mock(return_value="/the-redirect")
        flash = mocker.spy(db_request.session, "flash")

        with pytest.raises(HTTPSeeOther) as exc:
            views.delete_project(project, db_request)
        assert exc.value.headers["Location"] == "/the-redirect"

        flash.assert_called_once_with(
            "Could not delete project - "
            "acknowledge all of the consequences to continue",
            queue="error",
        )
        db_request.route_path.assert_called_once_with(
            "manage.project.settings", project_name=project.normalized_name
        )
        assert db_request.db.query(Project).filter(Project.name == "foo").count() == 1

    def test_delete_project_disallow_deletion(self, pyramid_request):
        project = pretend.stub(name="foo", normalized_name="foo")
        pyramid_request.flags = pretend.stub(
            enabled=pretend.call_recorder(lambda *a: True)
        )
        pyramid_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.delete_project(project, pyramid_request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert pyramid_request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISALLOW_DELETION)
        ]

        assert pyramid_request.session.flash.calls == [
            pretend.call(
                (
                    "Project deletion temporarily disabled. "
                    "See https://docs.pypi.org/about/security-and-internals/"
                    "#temporarily-disabled-features for details."
                ),
                queue="error",
            )
        ]

        assert pyramid_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]

    def test_get_user_role_in_project_single_role_owner(self, db_request):
        project = ProjectFactory.create(name="foo")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )
        db_request.user = UserFactory.create()
        RoleFactory(user=db_request.user, project=project, role_name="Owner")

        res = views.get_user_role_in_project(project, db_request.user, db_request)
        assert res == "Owner"

    def test_get_user_role_in_project_single_role_maintainer(self, db_request):
        project = ProjectFactory.create(name="foo")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )
        db_request.user = UserFactory.create()
        RoleFactory(user=db_request.user, project=project, role_name="Maintainer")

        res = views.get_user_role_in_project(project, db_request.user, db_request)
        assert res == "Maintainer"

    def test_get_user_role_in_project_org_owner(self, db_request):
        organization = OrganizationFactory.create(name="baz")
        project = ProjectFactory.create(name="foo")
        OrganizationProjectFactory.create(organization=organization, project=project)
        db_request.user = UserFactory.create()
        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )

        res = views.get_user_role_in_project(project, db_request.user, db_request)
        assert res == "Owner"

    def test_get_user_role_in_project_team_project_owner(self, db_request):
        organization = OrganizationFactory.create(name="baz")
        team = TeamFactory(organization=organization)
        project = ProjectFactory.create(name="foo")
        OrganizationProjectFactory.create(organization=organization, project=project)
        db_request.user = UserFactory.create()
        OrganizationRoleFactory.create(
            organization=organization,
            user=db_request.user,
            role_name=OrganizationRoleType.Member,
        )
        TeamRoleFactory.create(team=team, user=db_request.user)
        TeamProjectRoleFactory.create(
            team=team,
            project=project,
            role_name=TeamProjectRoleType.Owner,
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )

        res = views.get_user_role_in_project(project, db_request.user, db_request)
        assert res == "Owner"

    def test_delete_project(self, monkeypatch, db_request):
        project = ProjectFactory.create(name="foo")

        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST["confirm_project_name"] = project.name
        db_request.POST.update(dict.fromkeys(DELETE_PROJECT_ACKNOWLEDGMENTS, "on"))
        db_request.user = UserFactory.create()

        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        get_user_role_in_project = pretend.call_recorder(
            lambda project, user, req: "Owner"
        )
        monkeypatch.setattr(views, "get_user_role_in_project", get_user_role_in_project)

        send_removed_project_email = pretend.call_recorder(lambda req, user, **k: None)
        monkeypatch.setattr(
            views, "send_removed_project_email", send_removed_project_email
        )

        result = views.delete_project(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Deleted the project 'foo'", queue="success")
        ]
        assert db_request.route_path.calls == [pretend.call("manage.projects")]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert get_user_role_in_project.calls == [
            pretend.call(project, db_request.user, db_request),
            pretend.call(project, db_request.user, db_request),
        ]

        assert send_removed_project_email.calls == [
            pretend.call(
                db_request,
                db_request.user,
                project_name=project.name,
                submitter_name=db_request.user.username,
                submitter_role="Owner",
                recipient_role="Owner",
            )
        ]
        assert not (db_request.db.query(Project).filter(Project.name == "foo").count())

    def test_delete_project_sends_emails_to_owners(self, monkeypatch, db_request):
        organization = OrganizationFactory.create(name="baz")
        project = ProjectFactory.create(name="foo")
        OrganizationProjectFactory.create(organization=organization, project=project)

        db_request.user = UserFactory.create(username="owner1")
        OrganizationRoleFactory.create(
            organization=organization,
            user=db_request.user,
            role_name=OrganizationRoleType.Owner,
        )

        # Add a second Owner
        owner2 = UserFactory.create(username="owner2")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner2,
            role_name=OrganizationRoleType.Owner,
        )
        # Add a Manager, who won't receive the email
        manager = UserFactory.create()
        OrganizationRoleFactory.create(
            organization=organization,
            user=manager,
            role_name=OrganizationRoleType.Manager,
        )

        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST["confirm_project_name"] = project.name
        db_request.POST.update(dict.fromkeys(DELETE_PROJECT_ACKNOWLEDGMENTS, "on"))

        get_user_role_in_project = pretend.call_recorder(
            lambda project, user, req: "Owner"
        )
        monkeypatch.setattr(views, "get_user_role_in_project", get_user_role_in_project)

        send_removed_project_email = pretend.call_recorder(lambda req, user, **k: None)
        monkeypatch.setattr(
            views, "send_removed_project_email", send_removed_project_email
        )

        result = views.delete_project(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Deleted the project 'foo'", queue="success")
        ]
        assert db_request.route_path.calls == [pretend.call("manage.projects")]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert get_user_role_in_project.calls == [
            pretend.call(project, db_request.user, db_request),
            pretend.call(project, db_request.user, db_request),
            pretend.call(project, owner2, db_request),
        ]

        assert send_removed_project_email.calls == [
            pretend.call(
                db_request,
                db_request.user,
                project_name=project.name,
                submitter_name=db_request.user.username,
                submitter_role="Owner",
                recipient_role="Owner",
            ),
            pretend.call(
                db_request,
                owner2,
                project_name=project.name,
                submitter_name=db_request.user.username,
                submitter_role="Owner",
                recipient_role="Owner",
            ),
        ]
        assert not (db_request.db.query(Project).filter(Project.name == "foo").count())


class TestManageProjectDocumentation:
    def test_manage_project_documentation(self):
        request = pretend.stub()
        project = pretend.stub()

        assert views.manage_project_documentation(project, request) == {
            "project": project
        }

    def test_destroy_project_docs_no_confirm(self):
        project = pretend.stub(normalized_name="foo")
        request = pretend.stub(
            POST={},
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        with pytest.raises(HTTPSeeOther) as exc:
            views.destroy_project_docs(project, request)
        assert exc.value.status_code == 303
        assert exc.value.headers["Location"] == "/foo/bar/"

        assert request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]

    def test_destroy_project_docs_wrong_confirm(self):
        project = pretend.stub(name="foo", normalized_name="foo")
        request = pretend.stub(
            POST={"confirm_project_name": "FOO"},
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        with pytest.raises(HTTPSeeOther) as exc:
            views.destroy_project_docs(project, request)
        assert exc.value.status_code == 303
        assert exc.value.headers["Location"] == "/foo/bar/"

        assert request.session.flash.calls == [
            pretend.call(
                "Could not delete project - 'FOO' is not the same as 'foo'",
                queue="error",
            )
        ]

    def test_destroy_project_docs(self, db_request):
        project = ProjectFactory.create(name="foo")
        remove_documentation_recorder = pretend.stub(
            delay=pretend.call_recorder(lambda *a, **kw: None)
        )
        task = pretend.call_recorder(lambda *a, **kw: remove_documentation_recorder)

        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST["confirm_project_name"] = project.name
        db_request.user = UserFactory.create()
        db_request.task = task

        result = views.destroy_project_docs(project, db_request)

        assert remove_documentation_recorder.delay.calls == [
            pretend.call(project.name),
            pretend.call(project.normalized_name),
        ]

        assert db_request.session.flash.calls == [
            pretend.call("Deleted docs for project 'foo'", queue="success")
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.documentation", project_name="foo")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert not (
            db_request.db.query(Project).filter(Project.name == "foo").first().has_docs
        )


class TestManageProjectReleases:
    def test_manage_project_releases(self, db_request):
        project = ProjectFactory.create(name="foobar")
        release = ReleaseFactory.create(project=project, version="1.0.0")
        release_file = FileFactory.create(
            release=release,
            filename=f"foobar-{release.version}.tar.gz",
            packagetype="sdist",
        )
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))

        assert views.manage_project_releases(project, db_request) == {
            "project": project,
            "version_to_file_counts": {
                release.version: {"total": 1, release_file.packagetype: 1}
            },
        }


class TestManageProjectRelease:
    def test_manage_project_release(self):
        files = pretend.stub()
        project = pretend.stub()
        release = pretend.stub(
            project=project, files=pretend.stub(all=lambda: files), yanked=False
        )
        request = pretend.stub()
        view = views.ManageProjectRelease(release, request)

        assert view.manage_project_release() == {
            "project": project,
            "release": release,
            "files": files,
        }

    @pytest.mark.parametrize(
        "method",
        [
            "yank_project_release",
            "unyank_project_release",
            "delete_project_release",
            "delete_project_release_file",
        ],
    )
    def test_release_mutations_blocked_when_quarantined(self, pyramid_request, method):
        release = pretend.stub(
            version="1.2.3",
            lifecycle_status=LifecycleStatus.QuarantineEnter,
            yanked=False,
            project=pretend.stub(name="foobar"),
        )
        pyramid_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        view = views.ManageProjectRelease(release, pyramid_request)
        result = getattr(view, method)()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                "This release is in quarantine and cannot be modified.",
                queue="error",
            )
        ]
        assert pyramid_request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]
        # Yank state is untouched
        assert release.yanked is False

    def test_delete_project_release_disallow_deletion(
        self, monkeypatch, pyramid_request
    ):
        release = pretend.stub(
            version="1.2.3",
            canonical_version="1.2.3",
            lifecycle_status=None,
            project=pretend.stub(
                name="foobar", record_event=pretend.call_recorder(lambda *a, **kw: None)
            ),
        )
        pyramid_request.flags = pretend.stub(
            enabled=pretend.call_recorder(lambda *a: True)
        )
        pyramid_request.method = "POST"
        pyramid_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        view = views.ManageProjectRelease(release, pyramid_request)
        result = view.delete_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert pyramid_request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISALLOW_DELETION)
        ]

        assert pyramid_request.session.flash.calls == [
            pretend.call(
                (
                    "Project deletion temporarily disabled. "
                    "See https://docs.pypi.org/about/security-and-internals/"
                    "#temporarily-disabled-features for details."
                ),
                queue="error",
            )
        ]

        assert pyramid_request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_yank_project_release(self, monkeypatch, db_request):
        user = UserFactory.create()
        project = ProjectFactory.create(name="foobar")
        RoleFactory.create(user=user, project=project)
        release = ReleaseFactory.create(project=project)
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)

        db_request.POST = {
            "confirm_yank_version": release.version,
            "yanked_reason": "Yanky Doodle went to town",
        }
        db_request.method = "POST"
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = user

        send_yanked_project_release_email = pretend.call_recorder(
            lambda req, contrib, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_yanked_project_release_email",
            send_yanked_project_release_email,
        )

        view = views.ManageProjectRelease(release, db_request)
        result = view.yank_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert release.yanked
        assert release.yanked_reason == "Yanky Doodle went to town"
        assert isinstance(release.yanked_date, dt.datetime)

        assert send_yanked_project_release_email.calls == [
            pretend.call(
                db_request,
                db_request.user,
                release=release,
                submitter_name=db_request.user.username,
                submitter_role="Owner",
                recipient_role="Owner",
            )
        ]
        entry = (
            db_request.db.query(JournalEntry)
            .options(joinedload(JournalEntry.submitted_by))
            .one()
        )
        assert entry.name == release.project.name
        assert entry.action == "yank release"
        assert entry.version == release.version
        assert entry.submitted_by == db_request.user
        assert db_request.session.flash.calls == [
            pretend.call(f"Yanked release {release.version!r}", queue="success")
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.releases", project_name=release.project.name)
        ]
        assert release.project.record_event.calls == [
            pretend.call(
                tag=EventTag.Project.ReleaseYank,
                request=db_request,
                additional={
                    "submitted_by": db_request.user.username,
                    "canonical_version": release.canonical_version,
                    "yanked_reason": "Yanky Doodle went to town",
                },
            )
        ]

    def test_yank_project_release_no_confirm(self, pyramid_request):
        release = pretend.stub(
            version="1.2.3",
            project=pretend.stub(name="foobar"),
            yanked=False,
            yanked_reason="",
            lifecycle_status=None,
        )
        pyramid_request.POST = {"confirm_yank_version": ""}
        pyramid_request.method = "POST"
        pyramid_request.flags = pretend.stub(
            enabled=pretend.call_recorder(lambda *a: False)
        )
        pyramid_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        view = views.ManageProjectRelease(release, pyramid_request)
        result = view.yank_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert not release.yanked
        assert not release.yanked_reason

        assert pyramid_request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]
        assert pyramid_request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_yank_project_release_bad_confirm(self, pyramid_request):
        release = pretend.stub(
            version="1.2.3",
            project=pretend.stub(name="foobar"),
            yanked=False,
            yanked_reason="",
            lifecycle_status=None,
        )
        pyramid_request.POST = {"confirm_yank_version": "invalid"}
        pyramid_request.method = "POST"
        pyramid_request.flags = pretend.stub(
            enabled=pretend.call_recorder(lambda *a: False)
        )
        pyramid_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        view = views.ManageProjectRelease(release, pyramid_request)
        result = view.yank_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert not release.yanked
        assert not release.yanked_reason

        assert pyramid_request.session.flash.calls == [
            pretend.call(
                "Could not yank release - "
                f"'invalid' is not the same as {release.version!r}",
                queue="error",
            )
        ]
        assert pyramid_request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_unyank_project_release(self, monkeypatch, db_request):
        user = UserFactory.create()
        project = ProjectFactory.create(name="foobar")
        RoleFactory.create(user=user, project=project)
        release = ReleaseFactory.create(project=project, yanked=True)
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)

        db_request.POST = {"confirm_unyank_version": release.version}
        db_request.method = "POST"
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = user

        send_unyanked_project_release_email = pretend.call_recorder(
            lambda req, contrib, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_unyanked_project_release_email",
            send_unyanked_project_release_email,
        )

        view = views.ManageProjectRelease(release, db_request)
        result = view.unyank_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert not release.yanked
        assert not release.yanked_reason
        assert release.yanked_date is None

        assert send_unyanked_project_release_email.calls == [
            pretend.call(
                db_request,
                db_request.user,
                release=release,
                submitter_name=db_request.user.username,
                submitter_role="Owner",
                recipient_role="Owner",
            )
        ]

        entry = (
            db_request.db.query(JournalEntry)
            .options(joinedload(JournalEntry.submitted_by))
            .one()
        )
        assert entry.name == release.project.name
        assert entry.action == "unyank release"
        assert entry.version == release.version
        assert entry.submitted_by == db_request.user

        assert db_request.session.flash.calls == [
            pretend.call(f"Un-yanked release {release.version!r}", queue="success")
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.releases", project_name=release.project.name)
        ]
        assert release.project.record_event.calls == [
            pretend.call(
                tag=EventTag.Project.ReleaseUnyank,
                request=db_request,
                additional={
                    "submitted_by": db_request.user.username,
                    "canonical_version": release.canonical_version,
                },
            )
        ]

    def test_unyank_project_release_no_confirm(self, pyramid_request):
        release = pretend.stub(
            version="1.2.3",
            project=pretend.stub(name="foobar"),
            yanked=True,
            yanked_reason="",
            lifecycle_status=None,
        )
        pyramid_request.POST = {
            "confirm_unyank_version": "",
            "yanked_reason": "Yanky Doodle went to town",
        }
        pyramid_request.method = "POST"
        pyramid_request.flags = pretend.stub(
            enabled=pretend.call_recorder(lambda *a: False)
        )
        pyramid_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        view = views.ManageProjectRelease(release, pyramid_request)
        result = view.unyank_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert release.yanked
        assert not release.yanked_reason

        assert pyramid_request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]
        assert pyramid_request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_unyank_project_release_bad_confirm(self, pyramid_request):
        release = pretend.stub(
            version="1.2.3",
            project=pretend.stub(name="foobar"),
            yanked=True,
            yanked_reason="Old reason",
            lifecycle_status=None,
        )
        pyramid_request.POST = {
            "confirm_unyank_version": "invalid",
            "yanked_reason": "New reason",
        }
        pyramid_request.method = "POST"
        pyramid_request.flags = pretend.stub(
            enabled=pretend.call_recorder(lambda *a: False)
        )
        pyramid_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        view = views.ManageProjectRelease(release, pyramid_request)
        result = view.unyank_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert release.yanked
        assert release.yanked_reason == "Old reason"

        assert pyramid_request.session.flash.calls == [
            pretend.call(
                "Could not un-yank release - "
                f"'invalid' is not the same as {release.version!r}",
                queue="error",
            )
        ]
        assert pyramid_request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_delete_project_release(self, monkeypatch, db_request):
        user = UserFactory.create()
        project = ProjectFactory.create(name="foobar")
        RoleFactory.create(user=user, project=project)
        release = ReleaseFactory.create(project=project, yanked=True)
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)

        db_request.POST = {
            "confirm_delete_version": release.version,
            **dict.fromkeys(DELETE_RELEASE_ACKNOWLEDGMENTS, "on"),
        }
        db_request.method = "POST"
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = user

        send_removed_project_release_email = pretend.call_recorder(
            lambda req, contrib, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_removed_project_release_email",
            send_removed_project_release_email,
        )

        view = views.ManageProjectRelease(release, db_request)
        result = view.delete_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert send_removed_project_release_email.calls == [
            pretend.call(
                db_request,
                db_request.user,
                release=release,
                submitter_name=db_request.user.username,
                submitter_role="Owner",
                recipient_role="Owner",
            )
        ]

        assert db_request.db.query(Release).all() == []
        entry = (
            db_request.db.query(JournalEntry)
            .options(joinedload(JournalEntry.submitted_by))
            .one()
        )
        assert entry.name == release.project.name
        assert entry.action == "remove release"
        assert entry.version == release.version
        assert entry.submitted_by == db_request.user

        assert db_request.session.flash.calls == [
            pretend.call(f"Deleted release {release.version!r}", queue="success")
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.releases", project_name=release.project.name)
        ]
        assert release.project.record_event.calls == [
            pretend.call(
                tag=EventTag.Project.ReleaseRemove,
                request=db_request,
                additional={
                    "submitted_by": db_request.user.username,
                    "canonical_version": release.canonical_version,
                },
            )
        ]

    def test_delete_project_release_no_confirm(self, pyramid_request):
        release = pretend.stub(
            version="1.2.3",
            project=pretend.stub(name="foobar"),
            lifecycle_status=None,
        )
        pyramid_request.POST = {"confirm_delete_version": ""}
        pyramid_request.method = "POST"
        pyramid_request.db = pretend.stub(delete=pretend.call_recorder(lambda a: None))
        pyramid_request.flags = pretend.stub(
            enabled=pretend.call_recorder(lambda *a: False)
        )
        pyramid_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        view = views.ManageProjectRelease(release, pyramid_request)
        result = view.delete_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert pyramid_request.db.delete.calls == []
        assert pyramid_request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]
        assert pyramid_request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISALLOW_DELETION)
        ]
        assert pyramid_request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_delete_project_release_bad_confirm(self, pyramid_request):
        release = pretend.stub(
            version="1.2.3",
            project=pretend.stub(name="foobar"),
            lifecycle_status=None,
        )
        pyramid_request.POST = {"confirm_delete_version": "invalid"}
        pyramid_request.method = "POST"
        pyramid_request.db = pretend.stub(delete=pretend.call_recorder(lambda a: None))
        pyramid_request.flags = pretend.stub(
            enabled=pretend.call_recorder(lambda *a: False)
        )
        pyramid_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        view = views.ManageProjectRelease(release, pyramid_request)
        result = view.delete_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert pyramid_request.db.delete.calls == []
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                "Could not delete release - "
                f"'invalid' is not the same as {release.version!r}",
                queue="error",
            )
        ]
        assert pyramid_request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_delete_project_release_no_acknowledgments(self, db_request, mocker):
        """Acknowledgment checkboxes are enforced server-side, not just in the UI."""
        release = ReleaseFactory.create()
        db_request.method = "POST"
        db_request.POST = {"confirm_delete_version": release.version}
        db_request.route_path = mocker.Mock(return_value="/the-redirect")
        flash = mocker.spy(db_request.session, "flash")

        view = views.ManageProjectRelease(release, db_request)

        with pytest.raises(HTTPSeeOther) as exc:
            view.delete_project_release()
        assert exc.value.headers["Location"] == "/the-redirect"

        flash.assert_called_once_with(
            "Could not delete release - "
            "acknowledge all of the consequences to continue",
            queue="error",
        )
        db_request.route_path.assert_called_once_with(
            "manage.project.release",
            project_name=release.project.name,
            version=release.version,
        )
        assert (
            db_request.db.query(Release).filter(Release.id == release.id).count() == 1
        )

    def test_delete_project_release_file_disallow_deletion(self, pyramid_request):
        release = pretend.stub(
            version="1.2.3",
            project=pretend.stub(name="foobar"),
            lifecycle_status=None,
        )
        pyramid_request.method = "POST"
        pyramid_request.flags = pretend.stub(
            enabled=pretend.call_recorder(lambda *a: True)
        )
        pyramid_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        view = views.ManageProjectRelease(release, pyramid_request)
        result = view.delete_project_release_file()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert pyramid_request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISALLOW_DELETION)
        ]

        assert pyramid_request.session.flash.calls == [
            pretend.call(
                (
                    "Project deletion temporarily disabled. "
                    "See https://docs.pypi.org/about/security-and-internals/"
                    "#temporarily-disabled-features for details."
                ),
                queue="error",
            )
        ]
        assert pyramid_request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_delete_project_release_file(self, monkeypatch, db_request):
        user = UserFactory.create()

        project = ProjectFactory.create(name="foobar")
        release = ReleaseFactory.create(project=project)
        release_file = FileFactory.create(
            release=release, filename=f"foobar-{release.version}.tar.gz"
        )
        RoleFactory.create(project=project, user=user)

        db_request.POST = {
            "confirm_project_name": release.project.name,
            "file_id": release_file.id,
            **dict.fromkeys(DELETE_FILE_ACKNOWLEDGMENTS, "on"),
        }
        db_request.method = ("POST",)
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = user

        get_user_role_in_project = pretend.call_recorder(
            lambda project, user, req: "Owner"
        )
        monkeypatch.setattr(views, "get_user_role_in_project", get_user_role_in_project)

        send_removed_project_release_file_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_removed_project_release_file_email",
            send_removed_project_release_file_email,
        )

        view = views.ManageProjectRelease(release, db_request)

        result = view.delete_project_release_file()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert db_request.session.flash.calls == [
            pretend.call(f"Deleted file {release_file.filename!r}", queue="success")
        ]

        assert db_request.db.query(File).filter_by(id=release_file.id).first() is None
        assert (
            db_request.db.query(JournalEntry)
            .filter_by(
                name=project.name,
                version=release.version,
                action=f"remove file {release_file.filename}",
                submitted_by=user,
            )
            .one()
        )
        assert db_request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

        assert get_user_role_in_project.calls == [
            pretend.call(project, db_request.user, db_request),
            pretend.call(project, db_request.user, db_request),
        ]

        assert send_removed_project_release_file_email.calls == [
            pretend.call(
                db_request,
                db_request.user,
                file=release_file.filename,
                release=release,
                submitter_name=db_request.user.username,
                submitter_role="Owner",
                recipient_role="Owner",
            )
        ]

    def test_delete_project_release_file_no_confirm(self, pyramid_request):
        release = pretend.stub(
            version="1.2.3",
            project=pretend.stub(name="foobar", normalized_name="foobar"),
            lifecycle_status=None,
        )
        pyramid_request.POST = {"confirm_project_name": ""}
        pyramid_request.method = "POST"
        pyramid_request.db = pretend.stub(delete=pretend.call_recorder(lambda a: None))
        pyramid_request.flags = pretend.stub(
            enabled=pretend.call_recorder(lambda *a: False)
        )
        pyramid_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        view = views.ManageProjectRelease(release, pyramid_request)
        result = view.delete_project_release_file()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert pyramid_request.db.delete.calls == []
        assert pyramid_request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISALLOW_DELETION)
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]
        assert pyramid_request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_delete_project_release_file_not_found(self, db_request):
        project = ProjectFactory.create(name="foobar")
        release = ReleaseFactory.create(project=project)

        def no_result_found():
            raise NoResultFound

        db_request.POST = {"confirm_project_name": "whatever"}
        db_request.method = "POST"
        db_request.db = pretend.stub(
            delete=pretend.call_recorder(lambda a: None),
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(one=no_result_found)
            ),
        )
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        view = views.ManageProjectRelease(release, db_request)

        result = view.delete_project_release_file()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert db_request.db.delete.calls == []
        assert db_request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISALLOW_DELETION)
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Could not find file", queue="error")
        ]
        assert db_request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_delete_project_release_file_bad_confirm(self, db_request):
        project = ProjectFactory.create(name="foobar")
        release = ReleaseFactory.create(project=project, version="1.2.3")
        release_file = FileFactory.create(
            release=release, filename="foobar-1.2.3.tar.gz"
        )

        db_request.POST = {
            "confirm_project_name": "invalid",
            "file_id": str(release_file.id),
        }
        db_request.method = "POST"
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        view = views.ManageProjectRelease(release, db_request)

        result = view.delete_project_release_file()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert db_request.db.query(File).filter_by(id=release_file.id).one()
        assert db_request.session.flash.calls == [
            pretend.call(
                "Could not delete file - "
                f"'invalid' is not the same as {release.project.name!r}",
                queue="error",
            )
        ]
        assert db_request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_delete_project_release_file_no_acknowledgments(self, db_request, mocker):
        """Acknowledgment checkboxes are enforced server-side, not just in the UI."""
        release = ReleaseFactory.create()
        release_file = FileFactory.create(release=release)
        db_request.method = "POST"
        db_request.POST = {
            "confirm_project_name": release.project.name,
            "file_id": str(release_file.id),
        }
        db_request.route_path = mocker.Mock(return_value="/the-redirect")
        flash = mocker.spy(db_request.session, "flash")

        view = views.ManageProjectRelease(release, db_request)

        with pytest.raises(HTTPSeeOther) as exc:
            view.delete_project_release_file()
        assert exc.value.headers["Location"] == "/the-redirect"

        flash.assert_called_once_with(
            "Could not delete file - acknowledge all of the consequences to continue",
            queue="error",
        )
        db_request.route_path.assert_called_once_with(
            "manage.project.release",
            project_name=release.project.name,
            version=release.version,
        )
        assert db_request.db.query(File).filter_by(id=release_file.id).one()


class TestManageProjectRoles:
    @pytest.fixture
    def organization(self, pyramid_user):
        organization = OrganizationFactory.create()
        OrganizationRoleFactory.create(
            organization=organization,
            user=pyramid_user,
            role_name=OrganizationRoleType.Owner,
        )
        return organization

    @pytest.fixture
    def organization_project(self, organization):
        project = ProjectFactory.create(organization=organization)
        OrganizationProjectFactory(organization=organization, project=project)
        return project

    @pytest.fixture
    def organization_member(self, organization):
        member = UserFactory.create()
        OrganizationRoleFactory.create(
            organization=organization,
            user=member,
            role_name=OrganizationRoleType.Member,
        )
        return member

    @pytest.fixture
    def organization_team(self, organization, organization_member):
        team = TeamFactory(organization=organization)
        TeamRoleFactory.create(team=team, user=organization_member)
        return team

    def test_get_manage_project_roles(self, db_request):
        user_service = pretend.stub()
        db_request.find_service = pretend.call_recorder(
            lambda iface, context: user_service
        )
        form_obj = pretend.stub()
        form_class = pretend.call_recorder(lambda d, user_service: form_obj)

        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create()
        user_2 = UserFactory.create()
        role = RoleFactory.create(user=user, project=project)
        role_invitation = RoleInvitationFactory.create(user=user_2, project=project)

        result = views.manage_project_roles(project, db_request, _form_class=form_class)

        assert db_request.find_service.calls == [
            pretend.call(IOrganizationService, context=None),
            pretend.call(IUserService, context=None),
        ]
        assert form_class.calls == [
            pretend.call(db_request.POST, user_service=user_service)
        ]
        assert result == {
            "project": project,
            "roles": {role},
            "invitations": {role_invitation},
            "form": form_obj,
            "enable_internal_collaborator": False,
            "team_project_roles": set(),
            "internal_role_form": None,
        }

    def test_post_new_internal_team_role(
        self,
        db_request,
        organization_project,
        organization_team,
        organization_member,
        monkeypatch,
    ):
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "is_team": "true",
                "team_name": organization_team.name,
                "team_project_role_name": "Owner",
                "username": "",
                "role_name": "",
            }
        )

        send_team_collaborator_added_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            views,
            "send_team_collaborator_added_email",
            send_team_collaborator_added_email,
        )
        send_added_as_team_collaborator_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            views,
            "send_added_as_team_collaborator_email",
            send_added_as_team_collaborator_email,
        )

        result = views.manage_project_roles(organization_project, db_request)

        assert send_team_collaborator_added_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                team=organization_team,
                submitter=db_request.user,
                project_name=organization_project.name,
                role="Owner",
            )
        ]
        assert send_added_as_team_collaborator_email.calls == [
            pretend.call(
                db_request,
                {organization_member},
                team=organization_team,
                submitter=db_request.user,
                project_name=organization_project.name,
                role="Owner",
            )
        ]
        assert isinstance(result, HTTPSeeOther)

    def test_post_duplicate_internal_team_role(
        self,
        db_request,
        organization_project,
        organization_team,
        monkeypatch,
    ):
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "is_team": "true",
                "team_name": organization_team.name,
                "team_project_role_name": "Owner",
                "username": "",
                "role_name": "",
            }
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        team_project_role = TeamProjectRoleFactory.create(
            team=organization_team,
            project=organization_project,
            role_name=TeamProjectRoleType.Owner,
        )

        result = views.manage_project_roles(organization_project, db_request)
        form = result["form"]
        internal_role_form = result["internal_role_form"]

        # No additional roles are created
        assert team_project_role == db_request.db.query(TeamProjectRole).one()
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Team '{organization_team.name}' already has Owner role for project",
                queue="error",
            )
        ]
        assert result == {
            "project": organization_project,
            "roles": set(),
            "invitations": set(),
            "form": form,
            "enable_internal_collaborator": True,
            "team_project_roles": {team_project_role},
            "internal_role_form": internal_role_form,
        }

    def test_post_new_internal_role(
        self,
        db_request,
        organization_project,
        organization_member,
        monkeypatch,
    ):
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "is_team": "false",
                "team_name": "",
                "team_project_role_name": "Owner",
                "username": organization_member.username,
                "role_name": "Owner",
            }
        )

        send_collaborator_added_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views,
            "send_collaborator_added_email",
            send_collaborator_added_email,
        )
        send_added_as_collaborator_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views,
            "send_added_as_collaborator_email",
            send_added_as_collaborator_email,
        )

        result = views.manage_project_roles(organization_project, db_request)

        assert send_collaborator_added_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                user=organization_member,
                submitter=db_request.user,
                project_name=organization_project.name,
                role="Owner",
            )
        ]
        assert send_added_as_collaborator_email.calls == [
            pretend.call(
                db_request,
                organization_member,
                submitter=db_request.user,
                project_name=organization_project.name,
                role="Owner",
            )
        ]
        assert isinstance(result, HTTPSeeOther)

    def test_post_new_role_validation_fails(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        user_2 = UserFactory.create(username="newuser")
        role = RoleFactory.create(user=user, project=project)
        role_invitation = RoleInvitationFactory.create(user=user_2, project=project)

        user_service = pretend.stub()
        db_request.find_service = pretend.call_recorder(
            lambda iface, context: user_service
        )
        db_request.method = "POST"
        form_obj = pretend.stub(validate=pretend.call_recorder(lambda: False))
        form_class = pretend.call_recorder(lambda d, user_service: form_obj)

        result = views.manage_project_roles(project, db_request, _form_class=form_class)

        assert db_request.find_service.calls == [
            pretend.call(IOrganizationService, context=None),
            pretend.call(IUserService, context=None),
        ]
        assert form_class.calls == [
            pretend.call(db_request.POST, user_service=user_service)
        ]
        assert form_obj.validate.calls == [pretend.call()]
        assert result == {
            "project": project,
            "roles": {role},
            "invitations": {role_invitation},
            "form": form_obj,
            "enable_internal_collaborator": False,
            "team_project_roles": set(),
            "internal_role_form": None,
        }

    def test_post_new_role(self, monkeypatch, db_request):
        project = ProjectFactory.create(name="foobar")
        new_user = UserFactory.create(username="new_user")
        EmailFactory.create(user=new_user, verified=True, primary=True)
        owner_1 = UserFactory.create(username="owner_1")
        owner_2 = UserFactory.create(username="owner_2")
        RoleFactory.create(user=owner_1, project=project, role_name="Owner")
        RoleFactory.create(user=owner_2, project=project, role_name="Owner")

        organization_service = pretend.stub()
        user_service = pretend.stub(
            find_userid=lambda username: new_user.id, get_user=lambda userid: new_user
        )
        token_service = pretend.stub(
            dumps=lambda data: "TOKEN", max_age=6 * 60 * 60, loads=lambda data: None
        )
        db_request.find_service = pretend.call_recorder(
            lambda iface, context=None, name=None: {
                IOrganizationService: organization_service,
                ITokenService: token_service,
                IUserService: user_service,
            }.get(iface)
        )
        db_request.method = "POST"
        db_request.POST = pretend.stub()
        db_request.user = owner_1
        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data=new_user.username),
            role_name=pretend.stub(data="Owner"),
        )
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        send_project_role_verification_email = pretend.call_recorder(
            lambda r, u, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_project_role_verification_email",
            send_project_role_verification_email,
        )

        result = views.manage_project_roles(project, db_request, _form_class=form_class)

        assert db_request.find_service.calls == [
            pretend.call(IOrganizationService, context=None),
            pretend.call(IUserService, context=None),
            pretend.call(ITokenService, name="email"),
        ]
        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(db_request.POST, user_service=user_service),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(f"Invitation sent to '{new_user.username}'", queue="success")
        ]

        # Only one role invitation is created
        assert (
            db_request.db.query(RoleInvitation)
            .filter(RoleInvitation.user == new_user)
            .filter(RoleInvitation.project == project)
            .one()
        )

        assert isinstance(result, HTTPSeeOther)

        assert send_project_role_verification_email.calls == [
            pretend.call(
                db_request,
                new_user,
                desired_role=form_obj.role_name.data,
                initiator_username=db_request.user.username,
                project_name=project.name,
                email_token=token_service.dumps(
                    {
                        "action": "email-project-role-verify",
                        "desired_role": form_obj.role_name.data,
                        "user_id": new_user.id,
                        "project_id": project.id,
                    }
                ),
                token_age=token_service.max_age,
            )
        ]

    def test_post_duplicate_role(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = RoleFactory.create(user=user, project=project, role_name="Owner")

        organization_service = pretend.stub()
        user_service = pretend.stub(
            find_userid=lambda username: user.id, get_user=lambda userid: user
        )
        token_service = pretend.stub(
            dumps=lambda data: "TOKEN", max_age=6 * 60 * 60, loads=lambda data: None
        )
        db_request.find_service = pretend.call_recorder(
            lambda iface, context=None, name=None: {
                IOrganizationService: organization_service,
                ITokenService: token_service,
                IUserService: user_service,
            }.get(iface)
        )
        db_request.method = "POST"
        db_request.POST = pretend.stub()
        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data=user.username),
            role_name=pretend.stub(data=role.role_name),
        )
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.manage_project_roles(project, db_request, _form_class=form_class)

        assert db_request.find_service.calls == [
            pretend.call(IOrganizationService, context=None),
            pretend.call(IUserService, context=None),
        ]
        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(db_request.POST, user_service=user_service),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "User 'testuser' already has Owner role for project", queue="error"
            )
        ]

        # No additional roles are created
        assert role == db_request.db.query(Role).one()

        assert isinstance(result, HTTPSeeOther)

    def test_reinvite_role_after_expiration(self, monkeypatch, db_request):
        project = ProjectFactory.create(name="foobar")
        new_user = UserFactory.create(username="new_user")
        EmailFactory.create(user=new_user, verified=True, primary=True)
        owner_1 = UserFactory.create(username="owner_1")
        owner_2 = UserFactory.create(username="owner_2")
        RoleFactory.create(user=owner_1, project=project, role_name="Owner")
        RoleFactory.create(user=owner_2, project=project, role_name="Owner")
        RoleInvitationFactory.create(
            user=new_user, project=project, invite_status="expired"
        )

        organization_service = pretend.stub()
        user_service = pretend.stub(
            find_userid=lambda username: new_user.id, get_user=lambda userid: new_user
        )
        token_service = pretend.stub(
            dumps=lambda data: "TOKEN", max_age=6 * 60 * 60, loads=lambda data: None
        )
        db_request.find_service = pretend.call_recorder(
            lambda iface, context=None, name=None: {
                IOrganizationService: organization_service,
                ITokenService: token_service,
                IUserService: user_service,
            }.get(iface)
        )
        db_request.method = "POST"
        db_request.POST = pretend.stub()
        db_request.remote_addr = "10.10.10.10"
        db_request.user = owner_1
        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data=new_user.username),
            role_name=pretend.stub(data="Owner"),
        )
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        send_project_role_verification_email = pretend.call_recorder(
            lambda r, u, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_project_role_verification_email",
            send_project_role_verification_email,
        )

        result = views.manage_project_roles(project, db_request, _form_class=form_class)

        assert db_request.find_service.calls == [
            pretend.call(IOrganizationService, context=None),
            pretend.call(IUserService, context=None),
            pretend.call(ITokenService, name="email"),
        ]
        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(db_request.POST, user_service=user_service),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(f"Invitation sent to '{new_user.username}'", queue="success")
        ]

        # Only one role invitation is created
        assert (
            db_request.db.query(RoleInvitation)
            .filter(RoleInvitation.user == new_user)
            .filter(RoleInvitation.project == project)
            .one()
        )

        assert isinstance(result, HTTPSeeOther)

        assert send_project_role_verification_email.calls == [
            pretend.call(
                db_request,
                new_user,
                desired_role=form_obj.role_name.data,
                initiator_username=db_request.user.username,
                project_name=project.name,
                email_token=token_service.dumps(
                    {
                        "action": "email-project-role-verify",
                        "desired_role": form_obj.role_name.data,
                        "user_id": new_user.id,
                        "project_id": project.id,
                    }
                ),
                token_age=token_service.max_age,
            )
        ]

    @pytest.mark.parametrize("stored_token", ["", "unverifiable"])
    def test_reinvite_role_with_unreadable_token(
        self, db_request, mocker, stored_token
    ):
        """
        A pending invitation whose token can't be read is replaced with a new one.
        """
        project = ProjectFactory.create(name="foobar")
        new_user = UserFactory.create(username="new_user")
        EmailFactory.create(user=new_user, verified=True, primary=True)
        owner = UserFactory.create(username="owner")
        RoleFactory.create(user=owner, project=project, role_name="Owner")
        if stored_token:
            other = TokenService(secret="other", salt="email", max_age=21600)
            stored_token = other.dumps({})
        invite = RoleInvitationFactory.create(
            user=new_user, project=project, token=stored_token
        )
        db_request.method = "POST"
        db_request.POST = MultiDict({"username": "new_user", "role_name": "Owner"})
        db_request.user = owner
        mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="/manage/roles"
        )
        flash = mocker.spy(db_request.session, "flash")
        send_email = mocker.patch.object(
            views, "send_project_role_verification_email", autospec=True
        )

        result = views.manage_project_roles(project, db_request)

        assert isinstance(result, HTTPSeeOther)
        flash.assert_called_once_with("Invitation sent to 'new_user'", queue="success")
        assert invite.invite_status == RoleInvitationStatus.Pending
        assert invite.token != stored_token
        send_email.assert_called_once()

    @pytest.mark.parametrize("with_email", [True, False])
    def test_post_unverified_email(self, db_request, with_email):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        if with_email:
            EmailFactory.create(user=user, verified=False, primary=True)

        organization_service = pretend.stub()
        user_service = pretend.stub(
            find_userid=lambda username: user.id, get_user=lambda userid: user
        )
        token_service = pretend.stub(
            dumps=lambda data: "TOKEN",
            max_age=6 * 60 * 60,
            loads=lambda data: None,
        )
        db_request.find_service = pretend.call_recorder(
            lambda iface, context=None, name=None: {
                IOrganizationService: organization_service,
                ITokenService: token_service,
                IUserService: user_service,
            }.get(iface)
        )
        db_request.method = "POST"
        db_request.POST = pretend.stub()
        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data=user.username),
            role_name=pretend.stub(data="Owner"),
        )
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.manage_project_roles(project, db_request, _form_class=form_class)

        assert db_request.find_service.calls == [
            pretend.call(IOrganizationService, context=None),
            pretend.call(IUserService, context=None),
            pretend.call(ITokenService, name="email"),
        ]
        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(db_request.POST, user_service=user_service),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "User 'testuser' does not have a verified primary email address "
                "and cannot be added as a Owner for project",
                queue="error",
            )
        ]

        # No additional roles are created
        assert db_request.db.query(Role).all() == []

        assert isinstance(result, HTTPSeeOther)

    def test_cannot_reinvite_role(self, db_request):
        project = ProjectFactory.create(name="foobar")
        new_user = UserFactory.create(username="new_user")
        EmailFactory.create(user=new_user, verified=True, primary=True)
        owner_1 = UserFactory.create(username="owner_1")
        owner_2 = UserFactory.create(username="owner_2")
        RoleFactory.create(user=owner_1, project=project, role_name="Owner")
        RoleFactory.create(user=owner_2, project=project, role_name="Owner")
        RoleInvitationFactory.create(
            user=new_user, project=project, invite_status="pending"
        )

        organization_service = pretend.stub()
        user_service = pretend.stub(
            find_userid=lambda username: new_user.id, get_user=lambda userid: new_user
        )
        token_service = pretend.stub(
            dumps=lambda data: "TOKEN",
            max_age=6 * 60 * 60,
            loads=lambda data: {"desired_role": "Maintainer"},
        )
        db_request.find_service = pretend.call_recorder(
            lambda iface, context=None, name=None: {
                IOrganizationService: organization_service,
                ITokenService: token_service,
                IUserService: user_service,
            }.get(iface)
        )
        db_request.method = "POST"
        db_request.POST = pretend.stub()
        db_request.remote_addr = "10.10.10.10"
        db_request.user = owner_1
        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data=new_user.username),
            role_name=pretend.stub(data="Owner"),
        )
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.manage_project_roles(project, db_request, _form_class=form_class)

        assert db_request.find_service.calls == [
            pretend.call(IOrganizationService, context=None),
            pretend.call(IUserService, context=None),
            pretend.call(ITokenService, name="email"),
        ]
        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(db_request.POST, user_service=user_service),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "User 'new_user' already has an active invite. Please try again later.",
                queue="error",
            )
        ]

        assert isinstance(result, HTTPSeeOther)


class TestRevokeRoleInvitation:
    def test_revoke_invitation(self, db_request, token_service):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        RoleInvitationFactory.create(user=user, project=project)
        owner_user = UserFactory.create()
        RoleFactory(user=owner_user, project=project, role_name="Owner")

        user_service = pretend.stub(get_user=lambda userid: user)
        token_service.loads = pretend.call_recorder(
            lambda token: {
                "action": "email-project-role-verify",
                "desired_role": "Maintainer",
                "user_id": user.id,
                "project_id": project.id,
                "submitter_id": db_request.user.id,
            }
        )
        db_request.find_service = pretend.call_recorder(
            lambda iface, context=None, name=None: {
                ITokenService: token_service,
                IUserService: user_service,
            }.get(iface)
        )
        db_request.method = "POST"
        db_request.POST = MultiDict({"user_id": user.id, "token": "TOKEN"})
        db_request.remote_addr = "10.10.10.10"
        db_request.user = owner_user
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/projects"
        )
        form_class = pretend.call_recorder(lambda *a, **kw: None)
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.revoke_project_role_invitation(
            project, db_request, _form_class=form_class
        )
        db_request.db.flush()

        assert not (
            db_request.db.query(RoleInvitation)
            .filter(RoleInvitation.user == user)
            .filter(RoleInvitation.project == project)
            .one_or_none()
        )
        assert db_request.session.flash.calls == [
            pretend.call(f"Invitation revoked from '{user.username}'.", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/projects"

    def test_invitation_does_not_exist(self, db_request, token_service):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        owner_user = UserFactory.create()
        RoleFactory(user=owner_user, project=project, role_name="Owner")

        user_service = pretend.stub(get_user=lambda userid: user)
        token_service.loads = pretend.call_recorder(
            lambda token: {
                "action": "email-project-role-verify",
                "desired_role": "Maintainer",
                "user_id": user.id,
                "project_id": project.id,
                "submitter_id": db_request.user.id,
            }
        )
        db_request.find_service = pretend.call_recorder(
            lambda iface, context=None, name=None: {
                ITokenService: token_service,
                IUserService: user_service,
            }.get(iface)
        )
        db_request.method = "POST"
        db_request.POST = MultiDict({"user_id": user.id, "token": "TOKEN"})
        db_request.remote_addr = "10.10.10.10"
        db_request.user = owner_user
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/projects"
        )
        form_class = pretend.call_recorder(lambda *a, **kw: None)
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.revoke_project_role_invitation(
            project, db_request, _form_class=form_class
        )
        db_request.db.flush()

        assert db_request.session.flash.calls == [
            pretend.call("Could not find role invitation.", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/projects"

    @pytest.mark.parametrize(
        ("stored_token", "message"),
        [
            ("expired", "Expired invitation for 'testuser' deleted."),
            ("invalid", "Invalid invitation for 'testuser' deleted."),
            ("", "Invalid invitation for 'testuser' deleted."),
        ],
    )
    def test_token_unusable(
        self, db_request, token_service, mocker, stored_token, message
    ):
        """
        An invitation whose token can't be loaded is deleted, and the revocation
        is recorded without a role.
        """
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        if stored_token == "expired":
            with freeze_time(
                dt.datetime.now(dt.UTC)
                - dt.timedelta(seconds=token_service.max_age + 1)
            ):
                stored_token = token_service.dumps({})
        elif stored_token == "invalid":
            other = TokenService(secret="other", salt="email", max_age=21600)
            stored_token = other.dumps({})
        RoleInvitationFactory.create(user=user, project=project, token=stored_token)
        owner_user = UserFactory.create()
        RoleFactory(user=owner_user, project=project, role_name="Owner")
        db_request.method = "POST"
        db_request.POST = MultiDict({"user_id": str(user.id)})
        db_request.user = owner_user
        mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="/manage/roles"
        )
        flash = mocker.spy(db_request.session, "flash")
        project_event = mocker.patch.object(project, "record_event", autospec=True)
        user_event = mocker.patch.object(user, "record_event", autospec=True)

        result = views.revoke_project_role_invitation(project, db_request)
        db_request.db.flush()

        assert (
            db_request.db.query(RoleInvitation)
            .filter(RoleInvitation.user == user)
            .filter(RoleInvitation.project == project)
            .one_or_none()
        ) is None
        assert (
            db_request.db.query(JournalEntry)
            .filter(JournalEntry.action.like("revoke_invite%"))
            .all()
        ) == []
        project_event.assert_called_once_with(
            tag=EventTag.Project.RoleRevokeInvite,
            request=db_request,
            additional={
                "submitted_by": owner_user.username,
                "role_name": None,
                "target_user": user.username,
            },
        )
        user_event.assert_called_once_with(
            tag=EventTag.Account.RoleRevokeInvite,
            request=db_request,
            additional={
                "submitted_by": owner_user.username,
                "project_name": project.name,
                "role_name": None,
            },
        )
        flash.assert_called_once_with(message, queue="success")
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/roles"


class TestChangeProjectRole:
    def test_change_role(self, db_request, monkeypatch):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = RoleFactory.create(user=user, project=project, role_name="Owner")
        new_role_name = "Maintainer"

        user_2 = UserFactory.create()

        db_request.method = "POST"
        db_request.user = user_2
        db_request.POST = MultiDict({"role_id": role.id, "role_name": new_role_name})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        send_collaborator_role_changed_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            views,
            "send_collaborator_role_changed_email",
            send_collaborator_role_changed_email,
        )
        send_role_changed_as_collaborator_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            views,
            "send_role_changed_as_collaborator_email",
            send_role_changed_as_collaborator_email,
        )

        result = views.change_project_role(project, db_request)

        assert role.role_name == new_role_name
        assert db_request.route_path.calls == [
            pretend.call("manage.project.roles", project_name=project.name)
        ]
        assert send_collaborator_role_changed_email.calls == [
            pretend.call(
                db_request,
                set(),
                user=user,
                submitter=user_2,
                project_name="foobar",
                role=new_role_name,
            )
        ]
        assert send_role_changed_as_collaborator_email.calls == [
            pretend.call(
                db_request,
                user,
                submitter=user_2,
                project_name="foobar",
                role=new_role_name,
            )
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Changed role", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        entry = (
            db_request.db.query(JournalEntry)
            .options(joinedload(JournalEntry.submitted_by))
            .one()
        )

        assert entry.name == project.name
        assert entry.action == "change Owner testuser to Maintainer"
        assert entry.submitted_by == db_request.user

    def test_change_role_invalid_role_name(self, pyramid_request):
        project = pretend.stub(name="foobar")

        pyramid_request.method = "POST"
        pyramid_request.POST = MultiDict(
            {"role_id": str(uuid.uuid4()), "role_name": "Invalid Role Name"}
        )
        pyramid_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )

        result = views.change_project_role(project, pyramid_request)

        assert pyramid_request.route_path.calls == [
            pretend.call("manage.project.roles", project_name=project.name)
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_change_missing_role(self, db_request):
        project = ProjectFactory.create(name="foobar")
        missing_role_id = str(uuid.uuid4())

        db_request.method = "POST"
        db_request.user = pretend.stub()
        db_request.POST = MultiDict({"role_id": missing_role_id, "role_name": "Owner"})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.change_project_role(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Could not find role", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_change_own_owner_role(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = RoleFactory.create(user=user, project=project, role_name="Owner")

        db_request.method = "POST"
        db_request.user = user
        db_request.POST = MultiDict({"role_id": role.id, "role_name": "Maintainer"})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.change_project_role(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Cannot remove yourself as Owner", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"


class TestDeleteProjectRole:
    def test_delete_role(self, db_request, monkeypatch):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = RoleFactory.create(user=user, project=project, role_name="Owner")
        user_2 = UserFactory.create()

        db_request.method = "POST"
        db_request.user = user_2
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        send_collaborator_removed_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views, "send_collaborator_removed_email", send_collaborator_removed_email
        )
        send_removed_as_collaborator_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            views,
            "send_removed_as_collaborator_email",
            send_removed_as_collaborator_email,
        )

        result = views.delete_project_role(project, db_request)

        assert db_request.route_path.calls == [
            pretend.call("manage.project.roles", project_name=project.name)
        ]
        assert db_request.db.query(Role).all() == []
        assert send_collaborator_removed_email.calls == [
            pretend.call(
                db_request, set(), user=user, submitter=user_2, project_name="foobar"
            )
        ]
        assert send_removed_as_collaborator_email.calls == [
            pretend.call(db_request, user, submitter=user_2, project_name="foobar")
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Removed collaborator", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        entry = (
            db_request.db.query(JournalEntry)
            .options(joinedload(JournalEntry.submitted_by))
            .one()
        )

        assert entry.name == project.name
        assert entry.action == "remove Owner testuser"
        assert entry.submitted_by == db_request.user

    def test_delete_missing_role(self, db_request):
        project = ProjectFactory.create(name="foobar")
        missing_role_id = str(uuid.uuid4())

        db_request.method = "POST"
        db_request.user = pretend.stub()
        db_request.POST = MultiDict({"role_id": missing_role_id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.delete_project_role(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Could not find role", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_delete_own_owner_role(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = RoleFactory.create(user=user, project=project, role_name="Owner")

        db_request.method = "POST"
        db_request.user = user
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.delete_project_role(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Cannot remove yourself as Sole Owner", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_delete_not_sole_owner_role(self, db_request, monkeypatch):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create()
        RoleFactory.create(user=user, project=project, role_name="Owner")
        user_2 = UserFactory.create(username="testuser")
        role_2 = RoleFactory.create(user=user_2, project=project, role_name="Owner")

        db_request.method = "POST"
        db_request.user = user_2
        db_request.POST = MultiDict({"role_id": role_2.id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        send_collaborator_removed_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views, "send_collaborator_removed_email", send_collaborator_removed_email
        )
        send_removed_as_collaborator_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            views,
            "send_removed_as_collaborator_email",
            send_removed_as_collaborator_email,
        )

        result = views.delete_project_role(project, db_request)

        assert db_request.route_path.calls == [pretend.call("manage.projects")]
        assert db_request.db.query(Role).filter(Role.user_id == user_2.id).all() == []
        assert send_collaborator_removed_email.calls == [
            pretend.call(
                db_request, {user}, user=user_2, submitter=user_2, project_name="foobar"
            )
        ]
        assert send_removed_as_collaborator_email.calls == [
            pretend.call(db_request, user_2, submitter=user_2, project_name="foobar")
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Removed collaborator", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        entry = (
            db_request.db.query(JournalEntry)
            .options(joinedload(JournalEntry.submitted_by))
            .one()
        )

        assert entry.name == project.name
        assert entry.action == "remove Owner testuser"
        assert entry.submitted_by == db_request.user

    def test_delete_non_owner_role(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = RoleFactory.create(user=user, project=project, role_name="Owner")

        some_other_user = UserFactory.create(username="someotheruser")
        some_other_project = ProjectFactory.create(name="someotherproject")

        db_request.method = "POST"
        db_request.user = some_other_user
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.delete_project_role(some_other_project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Could not find role", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"


class TestManageProjectHistory:
    def test_get(self, db_request, user_service):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project)
        file_ = FileFactory.create(release=release)
        # NOTE: intentionally out of order, to test sorting.
        events = [
            FileEventFactory.create(
                source=file_,
                tag="fake:event",
                time=dt.datetime(2018, 2, 5, 17, 18, 18, 462_634),
                additional={
                    "project_id": str(project.id),
                },
            ),
            ProjectEventFactory.create(
                source=project,
                tag="fake:event",
                time=dt.datetime(2017, 2, 5, 17, 18, 18, 462_634),
            ),
            ProjectEventFactory.create(
                source=project,
                tag="fake:event",
                time=dt.datetime(2019, 2, 5, 17, 18, 18, 462_634),
            ),
            FileEventFactory.create(
                source=file_,
                tag="fake:event",
                time=dt.datetime(2016, 2, 5, 17, 18, 18, 462_634),
                additional={
                    "project_id": str(project.id),
                },
            ),
        ]

        project_events_query = (
            db_request.db.query(Project.Event)
            .join(Project.Event.source)
            .filter(Project.Event.source_id == project.id)
        )
        file_events_query = (
            db_request.db.query(File.Event)
            .join(File.Event.source)
            .join(File.release)
            .filter(Release.project_id == project.id)
        )
        events_query = project_events_query.union_all(file_events_query).order_by(
            Project.Event.time.desc(), File.Event.time.desc()
        )

        events_page = SQLAlchemyORMPage(
            events_query,
            page=1,
            items_per_page=25,
            item_count=4,
            url_maker=paginate_url_factory(db_request),
        )

        assert views.manage_project_history(project, db_request) == {
            "events": events_page,
            "get_user": user_service.get_user,
            "project": project,
        }

        events_page = list(events_page)

        # NOTE: The Event -> Project.Event | File.Event mapping is broken
        # due to how Event subclasses are constructed, so we only test
        # the ordering here.
        assert [e.time for e in events_page] == [
            e.time for e in sorted(events, key=lambda e: e.time, reverse=True)
        ]

        # NOTE: This is a backstop for the bugged behavior above: when we
        # fix it, this will begin to fail.
        for event in events_page:
            assert isinstance(event, Project.Event)

    def test_raises_400_with_pagenum_type_str(self, monkeypatch, db_request):
        params = MultiDict({"page": "abc"})
        db_request.params = params

        events_query = pretend.stub()
        db_request.events_query = pretend.stub(
            events_query=lambda *a, **kw: events_query
        )

        page_obj = pretend.stub(page_count=10, item_count=1000)
        page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
        monkeypatch.setattr(views, "SQLAlchemyORMPage", page_cls)

        url_maker = pretend.stub()
        url_maker_factory = pretend.call_recorder(lambda request: url_maker)
        monkeypatch.setattr(views, "paginate_url_factory", url_maker_factory)

        project = ProjectFactory.create()
        with pytest.raises(HTTPBadRequest):
            views.manage_project_history(project, db_request)

        assert page_cls.calls == []

    def test_first_page(self, db_request, user_service):
        page_number = 1
        params = MultiDict({"page": page_number})
        db_request.params = params

        project = ProjectFactory.create()
        items_per_page = 25
        total_items = items_per_page + 2
        ProjectEventFactory.create_batch(total_items, source=project, tag="fake:event")
        project_events_query = (
            db_request.db.query(Project.Event)
            .join(Project.Event.source)
            .filter(Project.Event.source_id == project.id)
        )
        file_events_query = (
            db_request.db.query(File.Event)
            .join(File.Event.source)
            .join(File.release)
            .filter(Release.project_id == project.id)
        )
        events_query = project_events_query.union_all(file_events_query).order_by(
            Project.Event.time.desc(), File.Event.time.desc()
        )

        events_page = SQLAlchemyORMPage(
            events_query,
            page=page_number,
            items_per_page=items_per_page,
            item_count=total_items,
            url_maker=paginate_url_factory(db_request),
        )
        assert views.manage_project_history(project, db_request) == {
            "events": events_page,
            "get_user": user_service.get_user,
            "project": project,
        }

    def test_last_page(self, db_request, user_service):
        page_number = 2
        params = MultiDict({"page": page_number})
        db_request.params = params

        project = ProjectFactory.create()
        items_per_page = 25
        total_items = items_per_page + 2
        ProjectEventFactory.create_batch(total_items, source=project, tag="fake:event")
        project_events_query = (
            db_request.db.query(Project.Event)
            .join(Project.Event.source)
            .filter(Project.Event.source_id == project.id)
        )
        file_events_query = (
            db_request.db.query(File.Event)
            .join(File.Event.source)
            .join(File.release)
            .filter(Release.project_id == project.id)
        )
        events_query = project_events_query.union_all(file_events_query).order_by(
            Project.Event.time.desc(), File.Event.time.desc()
        )

        events_page = SQLAlchemyORMPage(
            events_query,
            page=page_number,
            items_per_page=items_per_page,
            item_count=total_items,
            url_maker=paginate_url_factory(db_request),
        )

        assert views.manage_project_history(project, db_request) == {
            "events": events_page,
            "get_user": user_service.get_user,
            "project": project,
        }

    def test_raises_404_with_out_of_range_page(self, db_request):
        page_number = 3
        params = MultiDict({"page": page_number})
        db_request.params = params

        project = ProjectFactory.create()
        items_per_page = 25
        total_items = items_per_page + 2
        ProjectEventFactory.create_batch(total_items, source=project, tag="fake:event")

        with pytest.raises(HTTPNotFound):
            assert views.manage_project_history(project, db_request)

    def test_only_returns_file_events_for_project(self, db_request):
        """File events are scoped via the release -> project relationship, so a
        file event belonging to another project must not leak into this
        project's history."""
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project)
        file_ = FileFactory.create(release=release)
        own_event = FileEventFactory.create(source=file_, tag="fake:event")

        # A file event on an unrelated project must not leak in. The factory
        # builds its own distinct project -> release -> file chain.
        FileEventFactory.create(tag="fake:event")

        result = views.manage_project_history(project, db_request)

        assert [event.id for event in result["events"]] == [own_event.id]


class TestArchiveProject:
    def test_archive(self, db_request):
        project = ProjectFactory.create(name="foo")
        user = UserFactory.create(username="testuser")

        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.method = "POST"
        db_request.user = user
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.archive_project_view(project, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert project.lifecycle_status == LifecycleStatus.ArchivedNoindex
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name=project.name)
        ]

    def test_unarchive_project(self, db_request):
        project = ProjectFactory.create(
            name="foo", lifecycle_status=LifecycleStatus.Archived
        )
        user = UserFactory.create(username="testuser")

        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.method = "POST"
        db_request.user = user
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.unarchive_project_view(project, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name=project.name)
        ]
        assert project.lifecycle_status is None

    def test_disallowed_archive(self, db_request):
        project = ProjectFactory.create(name="foo", lifecycle_status="quarantine-enter")
        user = UserFactory.create(username="testuser")

        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.method = "POST"
        db_request.user = user
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.archive_project_view(project, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Cannot archive project with status {project.lifecycle_status}",
                queue="error",
            )
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]
        assert project.lifecycle_status == "quarantine-enter"

    def test_disallowed_unarchive(self, db_request):
        project = ProjectFactory.create(name="foo", lifecycle_status="quarantine-enter")
        user = UserFactory.create(username="testuser")

        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.method = "POST"
        db_request.user = user
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.unarchive_project_view(project, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert db_request.session.flash.calls == [
            pretend.call("Can only unarchive an archived project", queue="error")
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]
        assert project.lifecycle_status == "quarantine-enter"
