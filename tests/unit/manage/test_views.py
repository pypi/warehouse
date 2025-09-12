# SPDX-License-Identifier: Apache-2.0

import base64
import datetime
import uuid

import pretend
import pytest

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPNotFound,
    HTTPOk,
    HTTPSeeOther,
    HTTPTooManyRequests,
)
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import joinedload
from webauthn.helpers import bytes_to_base64url
from webob.multidict import MultiDict

import warehouse.utils.otp as otp

from warehouse.accounts.interfaces import (
    IPasswordBreachedService,
    ITokenService,
    IUserService,
    TokenExpired,
)
from warehouse.admin.flags import AdminFlagValue
from warehouse.constants import MAX_FILESIZE, MAX_PROJECT_SIZE
from warehouse.events.tags import EventTag
from warehouse.macaroons import caveats
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.manage import views
from warehouse.manage.views import organizations as org_views
from warehouse.metrics.interfaces import IMetricsService
from warehouse.oidc.interfaces import TooManyOIDCRegistrations
from warehouse.oidc.models import (
    ActiveStatePublisher,
    GitHubPublisher,
    GitLabPublisher,
    GooglePublisher,
    OIDCPublisher,
)
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import (
    OrganizationRoleType,
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
    User,
)
from warehouse.rate_limiting import IRateLimiter
from warehouse.utils.paginate import paginate_url_factory

from ...common.db.accounts import EmailFactory
from ...common.db.organizations import (
    OrganizationFactory,
    OrganizationProjectFactory,
    OrganizationRoleFactory,
    TeamFactory,
    TeamProjectRoleFactory,
    TeamRoleFactory,
)
from ...common.db.packaging import (
    AlternateRepositoryFactory,
    FileEventFactory,
    FileFactory,
    JournalEntryFactory,
    ProjectEventFactory,
    ProjectFactory,
    ReleaseFactory,
    RoleFactory,
    RoleInvitationFactory,
    UserFactory,
)


class TestManageUnverifiedAccount:
    def test_manage_account(self, monkeypatch):
        user_service = pretend.stub()
        name = pretend.stub()
        request = pretend.stub(
            find_service=lambda *a, **kw: user_service,
            user=pretend.stub(name=name, has_primary_verified_email=False),
            help_url=pretend.call_recorder(lambda *a, **kw: "/the/url"),
            route_path=pretend.call_recorder(lambda *a, **kw: "/the/url"),
        )
        view = views.ManageUnverifiedAccountViews(request)

        assert view.manage_unverified_account() == {
            "help_url": "/the/url",
        }
        assert request.help_url.calls == [pretend.call(_anchor="account-recovery")]
        assert view.request == request
        assert view.user_service == user_service

    def test_verified_redirects(self):
        user_service = pretend.stub()
        user = pretend.stub(
            id=pretend.stub(),
            username="username",
            name="Name",
            has_primary_verified_email=True,
        )
        request = pretend.stub(
            find_service=lambda *a, **kw: user_service,
            user=user,
            help_url=pretend.call_recorder(lambda *a, **kw: "/the/url"),
            route_path=pretend.call_recorder(lambda *a, **kw: "/the/url"),
        )
        view = views.ManageUnverifiedAccountViews(request)

        result = view.manage_unverified_account()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the/url"


class TestManageAccount:
    @pytest.mark.parametrize(
        ("public_email", "expected_public_email"),
        [(None, ""), (pretend.stub(email="some@email.com"), "some@email.com")],
    )
    def test_default_response(self, monkeypatch, public_email, expected_public_email):
        breach_service = pretend.stub()
        user_service = pretend.stub()
        organization_service = pretend.stub()
        name = pretend.stub()
        user_id = pretend.stub()
        request = pretend.stub(
            find_service=lambda iface, **kw: {
                IPasswordBreachedService: breach_service,
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[iface],
            user=pretend.stub(name=name, id=user_id, public_email=public_email),
        )
        save_account_obj = pretend.stub()
        save_account_cls = pretend.call_recorder(lambda **kw: save_account_obj)
        monkeypatch.setattr(views, "SaveAccountForm", save_account_cls)

        add_email_obj = pretend.stub()
        add_email_cls = pretend.call_recorder(lambda **kw: add_email_obj)
        monkeypatch.setattr(views, "AddEmailForm", add_email_cls)

        change_pass_obj = pretend.stub()
        change_pass_cls = pretend.call_recorder(lambda **kw: change_pass_obj)
        monkeypatch.setattr(views, "ChangePasswordForm", change_pass_cls)

        view = views.ManageVerifiedAccountViews(request)

        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "active_projects", pretend.stub()
        )

        assert view.default_response == {
            "save_account_form": save_account_obj,
            "add_email_form": add_email_obj,
            "change_password_form": change_pass_obj,
            "active_projects": view.active_projects,
        }
        assert view.request == request
        assert view.user_service == user_service
        assert save_account_cls.calls == [
            pretend.call(
                name=name,
                public_email=expected_public_email,
                user_service=user_service,
                user_id=user_id,
            )
        ]
        assert add_email_cls.calls == [
            pretend.call(request=request, user_id=user_id, user_service=user_service)
        ]
        assert change_pass_cls.calls == [
            pretend.call(
                request=request,
                user_service=user_service,
                breach_service=breach_service,
            )
        ]

    def test_active_projects(self, db_request):
        user = UserFactory.create()
        another_user = UserFactory.create()

        db_request.user = user
        db_request.find_service = lambda *a, **kw: pretend.stub()

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

        view = views.ManageVerifiedAccountViews(db_request)

        assert view.active_projects == [with_sole_owner]

    def test_manage_account(self, monkeypatch):
        user_service = pretend.stub()
        name = pretend.stub()
        request = pretend.stub(
            find_service=lambda *a, **kw: user_service, user=pretend.stub(name=name)
        )
        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageVerifiedAccountViews(request)

        assert view.manage_account() == view.default_response
        assert view.request == request
        assert view.user_service == user_service

    def test_save_account(self, monkeypatch, pyramid_request):
        update_user = pretend.call_recorder(lambda *a, **kw: None)
        user_service = pretend.stub(update_user=update_user)
        pyramid_request.POST = {"name": "new name", "public_email": ""}
        pyramid_request.user = pretend.stub(
            id=pretend.stub(),
            name=pretend.stub(),
            emails=[
                pretend.stub(
                    primary=True, verified=True, public=True, email=pretend.stub()
                )
            ],
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        pyramid_request.find_service = lambda *a, **kw: user_service
        save_account_obj = pretend.stub(
            validate=lambda: True, data=pyramid_request.POST
        )
        monkeypatch.setattr(views, "SaveAccountForm", lambda *a, **kw: save_account_obj)
        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageVerifiedAccountViews(pyramid_request)

        assert isinstance(view.save_account(), HTTPSeeOther)
        assert pyramid_request.session.flash.calls == [
            pretend.call("Account details updated", queue="success")
        ]
        assert update_user.calls == [
            pretend.call(pyramid_request.user.id, **pyramid_request.POST)
        ]

    def test_save_account_validation_fails(self, monkeypatch):
        update_user = pretend.call_recorder(lambda *a, **kw: None)
        user_service = pretend.stub(update_user=update_user)
        request = pretend.stub(
            POST={"name": "new name", "public_email": ""},
            user=pretend.stub(id=pretend.stub(), name=pretend.stub()),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda *a, **kw: user_service,
        )
        save_account_obj = pretend.stub(validate=lambda: False)
        monkeypatch.setattr(views, "SaveAccountForm", lambda *a, **kw: save_account_obj)
        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageVerifiedAccountViews(request)

        assert view.save_account() == {
            **view.default_response,
            "save_account_form": save_account_obj,
        }
        assert request.session.flash.calls == []
        assert update_user.calls == []

    def test_add_email(self, monkeypatch, pyramid_request):
        new_email_address = "new@example.com"
        email = pretend.stub(id=pretend.stub(), email=new_email_address)
        existing_email_address = "existing@example.com"
        existing_email = pretend.stub(id=pretend.stub(), email=existing_email_address)
        user_service = pretend.stub(
            add_email=pretend.call_recorder(lambda *a, **kw: email),
        )
        pyramid_request.POST = {"email": new_email_address}
        pyramid_request.db = pretend.stub(flush=lambda: None)
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        pyramid_request.find_service = lambda a, **kw: user_service
        pyramid_request.user = pretend.stub(
            emails=[existing_email, email],
            username="username",
            name="Name",
            id=pretend.stub(),
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        monkeypatch.setattr(
            views,
            "AddEmailForm",
            lambda *a, **kw: pretend.stub(
                validate=lambda: True, email=pretend.stub(data=new_email_address)
            ),
        )

        send_email_verification_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views, "send_email_verification_email", send_email_verification_email
        )
        send_new_email_added_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views, "send_new_email_added_email", send_new_email_added_email
        )

        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageVerifiedAccountViews(pyramid_request)

        assert isinstance(view.add_email(), HTTPSeeOther)
        assert user_service.add_email.calls == [
            pretend.call(pyramid_request.user.id, new_email_address),
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                f"Email {new_email_address} added - check your email for "
                + "a verification link",
                queue="success",
            )
        ]
        assert send_email_verification_email.calls == [
            pretend.call(pyramid_request, (pyramid_request.user, email)),
        ]
        assert send_new_email_added_email.calls == [
            pretend.call(
                pyramid_request,
                (pyramid_request.user, existing_email),
                new_email_address=new_email_address,
            ),
        ]
        assert pyramid_request.user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.EmailAdd,
                request=pyramid_request,
                additional={"email": new_email_address},
            )
        ]

    def test_add_email_validation_fails(self, monkeypatch):
        email_address = "test@example.com"
        request = pretend.stub(
            POST={"email": email_address},
            db=pretend.stub(flush=lambda: None),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda a, **kw: pretend.stub(),
            user=pretend.stub(emails=[], name=pretend.stub(), id=pretend.stub()),
        )
        add_email_obj = pretend.stub(
            validate=lambda: False, email=pretend.stub(data=email_address)
        )
        add_email_cls = pretend.call_recorder(lambda *a, **kw: add_email_obj)
        monkeypatch.setattr(views, "AddEmailForm", add_email_cls)

        email_obj = pretend.stub(id=pretend.stub(), email=email_address)
        email_cls = pretend.call_recorder(lambda **kw: email_obj)
        monkeypatch.setattr(views, "Email", email_cls)

        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageVerifiedAccountViews(request)

        assert view.add_email() == {
            **view.default_response,
            "add_email_form": add_email_obj,
        }
        assert request.user.emails == []
        assert email_cls.calls == []
        assert request.session.flash.calls == []

    def test_delete_email(self, monkeypatch):
        email = pretend.stub(id=5, primary=False, email=pretend.stub())
        some_other_email = pretend.stub()
        user_service = pretend.stub(
            record_event=pretend.call_recorder(lambda *a, **kw: None)
        )
        request = pretend.stub(
            POST={"delete_email_id": str(email.id)},
            user=pretend.stub(
                id=pretend.stub(),
                emails=[email, some_other_email],
                name=pretend.stub(),
                record_event=pretend.call_recorder(lambda *a, **kw: None),
            ),
            db=pretend.stub(
                query=lambda a: pretend.stub(
                    filter=lambda *a: pretend.stub(one=lambda: email)
                )
            ),
            find_service=lambda *a, **kw: user_service,
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            remote_addr="0.0.0.0",
            path="request-path",
        )
        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageVerifiedAccountViews(request)

        assert isinstance(view.delete_email(), HTTPSeeOther)
        assert request.session.flash.calls == [
            pretend.call(f"Email address {email.email} removed", queue="success")
        ]
        assert request.user.emails == [some_other_email]
        assert request.user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.EmailRemove,
                request=request,
                additional={"email": email.email},
            )
        ]

    def test_delete_email_not_found(self, monkeypatch):
        email = pretend.stub()

        def raise_no_result():
            raise NoResultFound

        request = pretend.stub(
            POST={"delete_email_id": "999999999999"},
            user=pretend.stub(id=pretend.stub(), emails=[email], name=pretend.stub()),
            db=pretend.stub(
                query=lambda a: pretend.stub(
                    filter=lambda *a: pretend.stub(one=raise_no_result)
                )
            ),
            find_service=lambda *a, **kw: pretend.stub(),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )
        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageVerifiedAccountViews(request)

        assert view.delete_email() == view.default_response
        assert request.session.flash.calls == [
            pretend.call("Email address not found", queue="error")
        ]
        assert request.user.emails == [email]

    def test_delete_email_is_primary(self, monkeypatch):
        email = pretend.stub(primary=True)

        request = pretend.stub(
            POST={"delete_email_id": "99999"},
            user=pretend.stub(id=pretend.stub(), emails=[email], name=pretend.stub()),
            db=pretend.stub(
                query=lambda a: pretend.stub(
                    filter=lambda *a: pretend.stub(one=lambda: email)
                )
            ),
            find_service=lambda *a, **kw: pretend.stub(),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )
        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageVerifiedAccountViews(request)

        assert view.delete_email() == view.default_response
        assert request.session.flash.calls == [
            pretend.call("Cannot remove primary email address", queue="error")
        ]
        assert request.user.emails == [email]

    def test_change_primary_email(self, monkeypatch, db_request):
        user = UserFactory()
        user.record_event = pretend.call_recorder(lambda *a, **kw: None)
        old_primary = EmailFactory(primary=True, user=user, email="old")
        new_primary = EmailFactory(primary=False, verified=True, user=user, email="new")

        db_request.user = user

        user_service = pretend.stub()
        db_request.find_service = lambda *a, **kw: user_service
        db_request.POST = {"primary_email_id": str(new_primary.id)}
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageVerifiedAccountViews(db_request)

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_primary_email_change_email", send_email)

        assert isinstance(view.change_primary_email(), HTTPSeeOther)
        assert send_email.calls == [
            pretend.call(db_request, (db_request.user, old_primary))
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Email address {new_primary.email} set as primary", queue="success"
            )
        ]
        assert not old_primary.primary
        assert new_primary.primary
        assert user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.EmailPrimaryChange,
                request=db_request,
                additional={"old_primary": "old", "new_primary": "new"},
            )
        ]

    def test_change_primary_email_without_current(self, monkeypatch, db_request):
        user = UserFactory()
        user.record_event = pretend.call_recorder(lambda *a, **kw: None)
        new_primary = EmailFactory(primary=False, verified=True, user=user)

        db_request.user = user

        user_service = pretend.stub()
        db_request.find_service = lambda *a, **kw: user_service
        db_request.POST = {"primary_email_id": str(new_primary.id)}
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageVerifiedAccountViews(db_request)

        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_primary_email_change_email", send_email)

        assert isinstance(view.change_primary_email(), HTTPSeeOther)
        assert send_email.calls == []
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Email address {new_primary.email} set as primary", queue="success"
            )
        ]
        assert new_primary.primary
        assert db_request.user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.EmailPrimaryChange,
                request=db_request,
                additional={"old_primary": None, "new_primary": new_primary.email},
            )
        ]

    def test_change_primary_email_not_found(self, monkeypatch, db_request):
        user = UserFactory()
        old_primary = EmailFactory(primary=True, user=user)
        missing_email_id = 9999

        db_request.user = user
        db_request.find_service = lambda *a, **kw: pretend.stub()
        db_request.POST = {"primary_email_id": str(missing_email_id)}
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageVerifiedAccountViews(db_request)

        assert view.change_primary_email() == view.default_response
        assert db_request.session.flash.calls == [
            pretend.call("Email address not found", queue="error")
        ]
        assert old_primary.primary

    @pytest.mark.parametrize(
        ("has_primary_verified_email", "expected_redirect"),
        [
            (True, "manage.account"),
            (False, "manage.unverified-account"),
        ],
    )
    def test_reverify_email(
        self, monkeypatch, has_primary_verified_email, expected_redirect
    ):
        user = pretend.stub(
            id=pretend.stub(),
            username="username",
            name="Name",
            record_event=pretend.call_recorder(lambda *a, **kw: None),
            has_primary_verified_email=has_primary_verified_email,
        )
        email = pretend.stub(
            verified=False,
            email="email_address",
            user=user,
        )

        request = pretend.stub(
            POST={"reverify_email_id": "99999"},
            db=pretend.stub(
                query=lambda *a: pretend.stub(
                    filter=lambda *a: pretend.stub(one=lambda: email)
                )
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda svc, name=None, context=None: {
                IRateLimiter: pretend.stub(
                    test=pretend.call_recorder(lambda user_id: True),
                    hit=pretend.call_recorder(lambda user_id: None),
                )
            }.get(svc, pretend.stub()),
            user=user,
            remote_addr="0.0.0.0",
            path="request-path",
            route_path=pretend.call_recorder(lambda *a, **kw: "/foo/bar/"),
        )
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_email_verification_email", send_email)
        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageVerifiedAccountViews(request)

        assert isinstance(view.reverify_email(), HTTPSeeOther)
        assert request.session.flash.calls == [
            pretend.call("Verification email for email_address resent", queue="success")
        ]
        assert send_email.calls == [pretend.call(request, (request.user, email))]
        assert user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.EmailReverify,
                request=request,
                additional={"email": email.email},
            )
        ]
        assert request.route_path.calls == [pretend.call(expected_redirect)]

    def test_reverify_email_ratelimit_exceeded(self, monkeypatch):
        user = pretend.stub(
            id=pretend.stub(),
            username="username",
            name="Name",
            record_event=pretend.call_recorder(lambda *a, **kw: None),
            has_primary_verified_email=True,
        )

        email = pretend.stub(
            verified=False,
            email="email_address",
            user=user,
        )

        request = pretend.stub(
            POST={"reverify_email_id": "9999"},
            db=pretend.stub(
                query=lambda *a: pretend.stub(
                    filter=lambda *a: pretend.stub(one=lambda: email)
                )
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda svc, name=None, context=None: {
                IRateLimiter: pretend.stub(
                    test=pretend.call_recorder(lambda user_id: False),
                )
            }.get(svc, pretend.stub()),
            user=user,
            remote_addr="0.0.0.0",
            path="request-path",
            route_path=pretend.call_recorder(lambda *a, **kw: "/foo/bar/"),
        )
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_email_verification_email", send_email)
        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageVerifiedAccountViews(request)

        assert isinstance(view.reverify_email(), HTTPSeeOther)
        assert request.session.flash.calls == [
            pretend.call(
                (
                    "Too many incomplete attempts to verify email address(es) for "
                    f"{request.user.username}. Complete a pending "
                    "verification or wait before attempting again."
                ),
                queue="error",
            )
        ]
        assert send_email.calls == []
        assert email.user.record_event.calls == []

    @pytest.mark.parametrize("reverify_email_id", ["9999", "wutang"])
    @pytest.mark.parametrize(
        ("has_primary_verified_email", "expected"),
        [
            (True, "manage.account"),
            (False, "manage.unverified-account"),
        ],
    )
    def test_reverify_email_not_found(
        self, monkeypatch, reverify_email_id, has_primary_verified_email, expected
    ):
        def raise_no_result():
            raise NoResultFound

        request = pretend.stub(
            POST={"reverify_email_id": reverify_email_id},
            db=pretend.stub(
                query=lambda *a: pretend.stub(
                    filter=lambda *a: pretend.stub(one=raise_no_result)
                )
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda *a, **kw: pretend.stub(),
            user=pretend.stub(
                id=pretend.stub(), has_primary_verified_email=has_primary_verified_email
            ),
            route_path=pretend.call_recorder(lambda *a: "/some/url"),
        )
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_email_verification_email", send_email)
        view = views.ManageVerifiedAccountViews(request)

        assert isinstance(view.reverify_email(), HTTPSeeOther)
        assert request.session.flash.calls == [
            pretend.call("Email address not found", queue="error")
        ]
        assert send_email.calls == []
        assert request.route_path.calls == [pretend.call(expected)]

    def test_reverify_email_already_verified(self, monkeypatch):
        email = pretend.stub(verified=True, email="email_address")

        request = pretend.stub(
            POST={"reverify_email_id": "9999"},
            db=pretend.stub(
                query=lambda *a: pretend.stub(
                    filter=lambda *a: pretend.stub(one=lambda: email)
                )
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda *a, **kw: pretend.stub(),
            user=pretend.stub(
                id=pretend.stub(),
                has_primary_verified_email=True,
            ),
            path="request-path",
            route_path=pretend.call_recorder(lambda *a, **kw: "/foo/bar/"),
        )
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_email_verification_email", send_email)
        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageVerifiedAccountViews(request)

        assert isinstance(view.reverify_email(), HTTPSeeOther)
        assert request.session.flash.calls == [
            pretend.call("Email is already verified", queue="error")
        ]
        assert send_email.calls == []

    def test_change_password(self, monkeypatch):
        old_password = "0ld_p455w0rd"
        new_password = "n3w_p455w0rd"
        user_service = pretend.stub(
            update_user=pretend.call_recorder(lambda *a, **kw: None),
            get_password_timestamp=lambda uid: 0,
        )
        request = pretend.stub(
            POST={
                "password": old_password,
                "new_password": new_password,
                "password_confirm": new_password,
            },
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
                record_password_timestamp=lambda ts: None,
            ),
            find_service=lambda *a, **kw: user_service,
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                email=pretend.stub(),
                name=pretend.stub(),
                record_event=pretend.call_recorder(lambda *a, **kw: None),
            ),
            db=pretend.stub(
                flush=lambda: None,
                refresh=lambda obj: None,
            ),
            remote_addr="0.0.0.0",
            path="request-path",
        )
        change_pwd_obj = pretend.stub(
            validate=lambda: True, new_password=pretend.stub(data=new_password)
        )
        change_pwd_cls = pretend.call_recorder(lambda *a, **kw: change_pwd_obj)
        monkeypatch.setattr(views, "ChangePasswordForm", change_pwd_cls)

        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_password_change_email", send_email)
        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageVerifiedAccountViews(request)

        assert isinstance(view.change_password(), HTTPSeeOther)
        assert request.session.flash.calls == [
            pretend.call("Password updated", queue="success")
        ]
        assert send_email.calls == [pretend.call(request, request.user)]
        assert user_service.update_user.calls == [
            pretend.call(request.user.id, password=new_password)
        ]
        assert request.user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.PasswordChange,
                request=request,
            )
        ]

    def test_change_password_validation_fails(self, monkeypatch):
        old_password = "0ld_p455w0rd"
        new_password = "n3w_p455w0rd"
        user_service = pretend.stub(
            update_user=pretend.call_recorder(lambda *a, **kw: None)
        )
        request = pretend.stub(
            POST={
                "password": old_password,
                "new_password": new_password,
                "password_confirm": new_password,
            },
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda *a, **kw: user_service,
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                email=pretend.stub(),
                name=pretend.stub(),
            ),
        )
        change_pwd_obj = pretend.stub(
            validate=lambda: False, new_password=pretend.stub(data=new_password)
        )
        change_pwd_cls = pretend.call_recorder(lambda *a, **kw: change_pwd_obj)
        monkeypatch.setattr(views, "ChangePasswordForm", change_pwd_cls)

        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_password_change_email", send_email)
        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageVerifiedAccountViews(request)

        assert view.change_password() == {
            **view.default_response,
            "change_password_form": change_pwd_obj,
        }
        assert request.session.flash.calls == []
        assert send_email.calls == []
        assert user_service.update_user.calls == []

    def test_delete_account(self, monkeypatch, db_request):
        user = UserFactory.create()
        deleted_user = UserFactory.create(username="deleted-user")
        jid = JournalEntryFactory.create(submitted_by=user).id

        db_request.user = user
        db_request.params = {"confirm_password": user.password}
        db_request.find_service = lambda *a, **kw: pretend.stub()

        confirm_password_obj = pretend.stub(validate=lambda: True)
        confirm_password_cls = pretend.call_recorder(
            lambda *a, **kw: confirm_password_obj
        )
        monkeypatch.setattr(views, "ConfirmPasswordForm", confirm_password_cls)

        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", pretend.stub()
        )
        monkeypatch.setattr(views.ManageVerifiedAccountViews, "active_projects", [])
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_account_deletion_email", send_email)
        logout_response = pretend.stub()
        logout = pretend.call_recorder(lambda *a: logout_response)
        monkeypatch.setattr(views, "logout", logout)

        view = views.ManageVerifiedAccountViews(db_request)

        assert view.delete_account() == logout_response

        journal = (
            db_request.db.query(JournalEntry)
            .options(joinedload(JournalEntry.submitted_by))
            .filter_by(id=jid)
            .one()
        )

        assert journal.submitted_by == deleted_user
        assert db_request.db.query(User).all() == [deleted_user]
        assert send_email.calls == [pretend.call(db_request, user)]
        assert logout.calls == [pretend.call(db_request)]

    def test_delete_account_no_confirm(self, monkeypatch):
        request = pretend.stub(
            params={"confirm_password": ""},
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda *a, **kw: pretend.stub(),
        )

        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", pretend.stub()
        )

        view = views.ManageVerifiedAccountViews(request)

        assert view.delete_account() == view.default_response
        assert request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]

    def test_delete_account_wrong_confirm(self, monkeypatch):
        request = pretend.stub(
            params={"confirm_password": "invalid"},
            user=pretend.stub(username="username"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda *a, **kw: pretend.stub(),
        )

        confirm_password_obj = pretend.stub(validate=lambda: False)
        confirm_password_cls = pretend.call_recorder(
            lambda *a, **kw: confirm_password_obj
        )
        monkeypatch.setattr(views, "ConfirmPasswordForm", confirm_password_cls)

        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", pretend.stub()
        )

        view = views.ManageVerifiedAccountViews(request)

        assert view.delete_account() == view.default_response
        assert request.session.flash.calls == [
            pretend.call(
                "Could not delete account - Invalid credentials. Please try again.",
                queue="error",
            )
        ]

    def test_delete_account_has_active_projects(self, monkeypatch):
        request = pretend.stub(
            params={"confirm_password": "password"},
            user=pretend.stub(username="username"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda *a, **kw: pretend.stub(),
        )

        confirm_password_obj = pretend.stub(validate=lambda: True)
        confirm_password_cls = pretend.call_recorder(
            lambda *a, **kw: confirm_password_obj
        )
        monkeypatch.setattr(views, "ConfirmPasswordForm", confirm_password_cls)

        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "default_response", pretend.stub()
        )
        monkeypatch.setattr(
            views.ManageVerifiedAccountViews, "active_projects", [pretend.stub()]
        )

        view = views.ManageVerifiedAccountViews(request)

        assert view.delete_account() == view.default_response
        assert request.session.flash.calls == [
            pretend.call(
                "Cannot delete account with active project ownerships", queue="error"
            )
        ]


class Test2FA:
    def test_manage_two_factor(self):
        request = pretend.stub()
        assert views.manage_two_factor(request) == {}


class TestProvisionTOTP:
    def test_generate_totp_qr(self, monkeypatch):
        user_service = pretend.stub(get_totp_secret=lambda id: None)
        request = pretend.stub(
            session=pretend.stub(get_totp_secret=otp.generate_totp_secret),
            find_service=lambda interface, **kw: {IUserService: user_service}[
                interface
            ],
            user=pretend.stub(
                id=pretend.stub(),
                username="foobar",
                email=pretend.stub(),
                name=pretend.stub(),
                has_primary_verified_email=True,
            ),
            registry=pretend.stub(settings={"site.name": "not_a_real_site_name"}),
        )

        view = views.ProvisionTOTPViews(request)
        result = view.generate_totp_qr()

        assert isinstance(result, HTTPOk)
        assert result.content_type == "image/svg+xml"

    def test_generate_totp_qr_two_factor_not_allowed(self):
        user_service = pretend.stub()
        request = pretend.stub(
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda interface, **kw: {IUserService: user_service}[
                interface
            ],
            user=pretend.stub(has_primary_verified_email=False),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        view = views.ProvisionTOTPViews(request)
        result = view.generate_totp_qr()

        assert isinstance(result, HTTPSeeOther)
        assert result.status_code == 303
        assert result.headers["Location"] == "/foo/bar/"
        assert request.session.flash.calls == [
            pretend.call(
                "Verify your email to modify two factor authentication", queue="error"
            )
        ]

    @pytest.mark.parametrize("current_totp_secret", [b"foobar", None])
    def test_totp_provision(self, monkeypatch, current_totp_secret):
        user_service = pretend.stub(get_totp_secret=lambda id: current_totp_secret)
        request = pretend.stub(
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
                get_totp_secret=lambda: b"secret",
                clear_totp_secret=pretend.call_recorder(lambda: None),
            ),
            find_service=lambda interface, **kw: {IUserService: user_service}[
                interface
            ],
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                email=pretend.stub(),
                name=pretend.stub(),
                has_primary_verified_email=True,
                has_burned_recovery_codes=True,
            ),
            registry=pretend.stub(settings={"site.name": "not_a_real_site_name"}),
        )

        provision_totp_obj = pretend.stub(validate=lambda: True)
        provision_totp_cls = pretend.call_recorder(lambda *a, **kw: provision_totp_obj)
        monkeypatch.setattr(views, "ProvisionTOTPForm", provision_totp_cls)

        generate_totp_provisioning_uri = pretend.call_recorder(
            lambda a, b, **k: "not_a_real_uri"
        )
        monkeypatch.setattr(
            otp, "generate_totp_provisioning_uri", generate_totp_provisioning_uri
        )

        view = views.ProvisionTOTPViews(request)
        result = view.totp_provision()

        assert provision_totp_cls.calls == [pretend.call(totp_secret=b"secret")]
        assert request.session.clear_totp_secret.calls == [pretend.call()]
        assert result == {
            "provision_totp_secret": base64.b32encode(b"secret").decode(),
            "provision_totp_form": provision_totp_obj,
            "provision_totp_uri": "not_a_real_uri",
        }

    @pytest.mark.parametrize(
        ("user", "expected_flash_calls"),
        [
            (
                pretend.stub(
                    has_burned_recovery_codes=False, has_primary_verified_email=True
                ),
                [],
            ),
            (
                pretend.stub(
                    has_burned_recovery_codes=True, has_primary_verified_email=False
                ),
                [
                    pretend.call(
                        "Verify your email to modify two factor authentication",
                        queue="error",
                    )
                ],
            ),
        ],
    )
    def test_totp_provision_two_factor_not_allowed(self, user, expected_flash_calls):
        user_service = pretend.stub()
        request = pretend.stub(
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda interface, **kw: {IUserService: user_service}[
                interface
            ],
            user=user,
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        view = views.ProvisionTOTPViews(request)
        result = view.totp_provision()

        assert isinstance(result, HTTPSeeOther)
        assert result.status_code == 303
        assert result.headers["Location"] == "/foo/bar/"
        assert request.session.flash.calls == expected_flash_calls

    @pytest.mark.parametrize("current_totp_secret", [b"foobar", None])
    def test_validate_totp_provision(self, monkeypatch, current_totp_secret):
        user_service = pretend.stub(
            get_totp_secret=lambda id: current_totp_secret,
            update_user=pretend.call_recorder(lambda *a, **kw: None),
        )
        request = pretend.stub(
            POST={"totp_value": "123456"},
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
                get_totp_secret=lambda: b"secret",
                clear_totp_secret=lambda: None,
            ),
            find_service=lambda interface, **kw: {IUserService: user_service}[
                interface
            ],
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                email=pretend.stub(),
                name=pretend.stub(),
                has_primary_verified_email=True,
                record_event=pretend.call_recorder(lambda *a, **kw: None),
            ),
            route_path=lambda *a, **kw: "/foo/bar/",
            remote_addr="0.0.0.0",
        )

        provision_totp_obj = pretend.stub(validate=lambda: True)
        provision_totp_cls = pretend.call_recorder(lambda *a, **kw: provision_totp_obj)
        monkeypatch.setattr(views, "ProvisionTOTPForm", provision_totp_cls)

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_two_factor_added_email", send_email)

        view = views.ProvisionTOTPViews(request)
        result = view.validate_totp_provision()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar/"
        assert user_service.update_user.calls == [
            pretend.call(request.user.id, totp_secret=b"secret")
        ]
        assert request.session.flash.calls == [
            pretend.call(
                "Authentication application successfully set up", queue="success"
            )
        ]
        expected_record_event_calls = [
            pretend.call(
                tag=EventTag.Account.TwoFactorMethodAdded,
                request=request,
                additional={"method": "totp"},
            )
        ]
        if current_totp_secret:
            expected_record_event_calls.insert(
                0,
                pretend.call(
                    tag=EventTag.Account.TwoFactorMethodRemoved,
                    request=request,
                    additional={"method": "totp"},
                ),
            )
        assert request.user.record_event.calls == expected_record_event_calls
        assert send_email.calls == [
            pretend.call(request, request.user, method="totp"),
        ]

    def test_validate_totp_provision_invalid_form(self, monkeypatch):
        user_service = pretend.stub(get_totp_secret=lambda id: None)
        request = pretend.stub(
            POST={},
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
                get_totp_secret=lambda: b"secret",
            ),
            find_service=lambda *a, **kw: user_service,
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                email=pretend.stub(),
                name=pretend.stub(),
                has_primary_verified_email=True,
            ),
            registry=pretend.stub(settings={"site.name": "not_a_real_site_name"}),
        )

        provision_totp_obj = pretend.stub(
            validate=lambda: False, totp_value=pretend.stub(data="123456")
        )
        provision_totp_cls = pretend.call_recorder(lambda *a, **kw: provision_totp_obj)
        monkeypatch.setattr(views, "ProvisionTOTPForm", provision_totp_cls)

        generate_totp_provisioning_uri = pretend.call_recorder(
            lambda a, b, **k: "not_a_real_uri"
        )
        monkeypatch.setattr(
            otp, "generate_totp_provisioning_uri", generate_totp_provisioning_uri
        )

        view = views.ProvisionTOTPViews(request)
        result = view.validate_totp_provision()

        assert request.session.flash.calls == []
        assert result == {
            "provision_totp_secret": base64.b32encode(b"secret").decode(),
            "provision_totp_form": provision_totp_obj,
            "provision_totp_uri": "not_a_real_uri",
        }

    def test_validate_totp_provision_two_factor_not_allowed(self):
        user_service = pretend.stub()
        request = pretend.stub(
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda interface, **kw: {IUserService: user_service}[
                interface
            ],
            user=pretend.stub(has_primary_verified_email=False),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        view = views.ProvisionTOTPViews(request)
        result = view.validate_totp_provision()

        assert isinstance(result, HTTPSeeOther)
        assert result.status_code == 303
        assert result.headers["Location"] == "/foo/bar/"
        assert request.session.flash.calls == [
            pretend.call(
                "Verify your email to modify two factor authentication", queue="error"
            )
        ]

    def test_delete_totp(self, monkeypatch, db_request):
        user_service = pretend.stub(
            get_totp_secret=lambda id: b"secret",
            update_user=pretend.call_recorder(lambda *a, **kw: None),
        )
        request = pretend.stub(
            POST={"confirm_password": pretend.stub()},
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda *a, **kw: user_service,
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                email=pretend.stub(),
                name=pretend.stub(),
                totp_secret=b"secret",
                has_primary_verified_email=True,
                record_event=pretend.call_recorder(lambda *a, **kw: None),
                has_single_2fa=False,
            ),
            route_path=lambda *a, **kw: "/foo/bar/",
            remote_addr="0.0.0.0",
        )

        delete_totp_obj = pretend.stub(validate=lambda: True)
        delete_totp_cls = pretend.call_recorder(lambda *a, **kw: delete_totp_obj)
        monkeypatch.setattr(views, "DeleteTOTPForm", delete_totp_cls)

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_two_factor_removed_email", send_email)

        view = views.ProvisionTOTPViews(request)
        result = view.delete_totp()

        assert user_service.update_user.calls == [
            pretend.call(request.user.id, totp_secret=None)
        ]
        assert request.session.flash.calls == [
            pretend.call(
                "Authentication application removed from PyPI. "
                "Remember to remove PyPI from your application.",
                queue="success",
            )
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar/"
        assert request.user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.TwoFactorMethodRemoved,
                request=request,
                additional={"method": "totp"},
            )
        ]
        assert send_email.calls == [
            pretend.call(request, request.user, method="totp"),
        ]

    def test_delete_totp_bad_password(self, monkeypatch, db_request):
        user_service = pretend.stub(
            get_totp_secret=lambda id: b"secret",
            update_user=pretend.call_recorder(lambda *a, **kw: None),
        )
        request = pretend.stub(
            POST={"confirm_password": pretend.stub()},
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda *a, **kw: user_service,
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                email=pretend.stub(),
                name=pretend.stub(),
                has_primary_verified_email=True,
                has_single_2fa=False,
            ),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        delete_totp_obj = pretend.stub(validate=lambda: False)
        delete_totp_cls = pretend.call_recorder(lambda *a, **kw: delete_totp_obj)
        monkeypatch.setattr(views, "DeleteTOTPForm", delete_totp_cls)

        view = views.ProvisionTOTPViews(request)
        result = view.delete_totp()

        assert user_service.update_user.calls == []
        assert request.session.flash.calls == [
            pretend.call("Invalid credentials. Try again", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar/"

    def test_delete_totp_not_provisioned(self, monkeypatch, db_request):
        user_service = pretend.stub(
            get_totp_secret=lambda id: None,
            update_user=pretend.call_recorder(lambda *a, **kw: None),
        )
        request = pretend.stub(
            POST={"confirm_password": pretend.stub()},
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda *a, **kw: user_service,
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                email=pretend.stub(),
                name=pretend.stub(),
                has_primary_verified_email=True,
            ),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        delete_totp_obj = pretend.stub(validate=lambda: True)
        delete_totp_cls = pretend.call_recorder(lambda *a, **kw: delete_totp_obj)
        monkeypatch.setattr(views, "DeleteTOTPForm", delete_totp_cls)

        view = views.ProvisionTOTPViews(request)
        result = view.delete_totp()

        assert user_service.update_user.calls == []
        assert request.session.flash.calls == [
            pretend.call(
                "There is no authentication application to delete", queue="error"
            )
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar/"

    def test_delete_totp_two_factor_not_allowed(self):
        user_service = pretend.stub()
        request = pretend.stub(
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda interface, **kw: {IUserService: user_service}[
                interface
            ],
            user=pretend.stub(has_primary_verified_email=False),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        view = views.ProvisionTOTPViews(request)
        result = view.delete_totp()

        assert isinstance(result, HTTPSeeOther)
        assert result.status_code == 303
        assert result.headers["Location"] == "/foo/bar/"
        assert request.session.flash.calls == [
            pretend.call(
                "Verify your email to modify two factor authentication", queue="error"
            )
        ]

    def test_delete_totp_last_2fa(self, monkeypatch, db_request):
        user_service = pretend.stub(
            get_totp_secret=lambda id: b"secret",
            update_user=pretend.call_recorder(lambda *a, **kw: None),
        )
        request = pretend.stub(
            POST={"confirm_password": pretend.stub()},
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda *a, **kw: user_service,
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                email=pretend.stub(),
                name=pretend.stub(),
                has_primary_verified_email=True,
                has_single_2fa=True,
            ),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        view = views.ProvisionTOTPViews(request)
        result = view.delete_totp()

        assert user_service.update_user.calls == []
        assert request.session.flash.calls == [
            pretend.call("Cannot remove last 2FA method", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar/"


class TestProvisionWebAuthn:
    def test_get_webauthn_view(self):
        user_service = pretend.stub()
        request = pretend.stub(
            find_service=lambda *a, **kw: user_service,
            user=pretend.stub(has_burned_recovery_codes=True),
        )

        view = views.ProvisionWebAuthnViews(request)
        result = view.webauthn_provision()

        assert result == {}

    def test_get_webauthn_view_redirect(self):
        user_service = pretend.stub()
        request = pretend.stub(
            find_service=lambda *a, **kw: user_service,
            user=pretend.stub(has_burned_recovery_codes=False),
            route_path=lambda x: "/foo/bar",
        )

        view = views.ProvisionWebAuthnViews(request)
        result = view.webauthn_provision()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar"

    def test_get_webauthn_options(self):
        user_service = pretend.stub(
            get_webauthn_credential_options=pretend.call_recorder(
                lambda *a, **kw: {"not_real": "credential_options"}
            )
        )
        request = pretend.stub(
            user=pretend.stub(id=1234),
            session=pretend.stub(
                get_webauthn_challenge=pretend.call_recorder(lambda: "fake_challenge")
            ),
            find_service=lambda *a, **kw: user_service,
            registry=pretend.stub(settings={"site.name": "fake_site_name"}),
            domain="fake_domain",
        )

        view = views.ProvisionWebAuthnViews(request)
        result = view.webauthn_provision_options()

        assert result == {"not_real": "credential_options"}
        assert user_service.get_webauthn_credential_options.calls == [
            pretend.call(
                1234,
                challenge="fake_challenge",
                rp_name=request.registry.settings["site.name"],
                rp_id=request.domain,
            )
        ]

    def test_validate_webauthn_provision(self, monkeypatch):
        user_service = pretend.stub(
            add_webauthn=pretend.call_recorder(lambda *a, **kw: pretend.stub()),
        )
        request = pretend.stub(
            POST={},
            user=pretend.stub(
                id=1234,
                webauthn=None,
                record_event=pretend.call_recorder(lambda *a, **kw: None),
            ),
            session=pretend.stub(
                get_webauthn_challenge=pretend.call_recorder(lambda: "fake_challenge"),
                clear_webauthn_challenge=pretend.call_recorder(lambda: pretend.stub()),
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            find_service=lambda *a, **kw: user_service,
            domain="fake_domain",
            host_url="fake_host_url",
            remote_addr="0.0.0.0",
        )

        provision_webauthn_obj = pretend.stub(
            validate=lambda: True,
            validated_credential=pretend.stub(
                credential_id=b"fake_credential_id",
                credential_public_key=b"fake_public_key",
                sign_count=1,
            ),
            label=pretend.stub(data="fake_label"),
        )
        provision_webauthn_cls = pretend.call_recorder(
            lambda *a, **kw: provision_webauthn_obj
        )
        monkeypatch.setattr(views, "ProvisionWebAuthnForm", provision_webauthn_cls)

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_two_factor_added_email", send_email)

        view = views.ProvisionWebAuthnViews(request)
        result = view.validate_webauthn_provision()

        assert request.session.get_webauthn_challenge.calls == [pretend.call()]
        assert request.session.clear_webauthn_challenge.calls == [pretend.call()]
        assert user_service.add_webauthn.calls == [
            pretend.call(
                1234,
                label="fake_label",
                credential_id=bytes_to_base64url(b"fake_credential_id"),
                public_key=bytes_to_base64url(b"fake_public_key"),
                sign_count=1,
            )
        ]
        assert request.session.flash.calls == [
            pretend.call("Security device successfully set up", queue="success")
        ]
        assert result == {"success": "Security device successfully set up"}
        assert request.user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.TwoFactorMethodAdded,
                request=request,
                additional={
                    "method": "webauthn",
                    "label": provision_webauthn_obj.label.data,
                },
            )
        ]
        assert send_email.calls == [
            pretend.call(request, request.user, method="webauthn"),
        ]

    def test_validate_webauthn_provision_invalid_form(self, monkeypatch):
        user_service = pretend.stub(
            add_webauthn=pretend.call_recorder(lambda *a, **kw: pretend.stub())
        )
        request = pretend.stub(
            POST={},
            user=pretend.stub(id=1234, webauthn=None),
            session=pretend.stub(
                get_webauthn_challenge=pretend.call_recorder(lambda: "fake_challenge"),
                clear_webauthn_challenge=pretend.call_recorder(lambda: pretend.stub()),
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            find_service=lambda *a, **kw: user_service,
            domain="fake_domain",
            host_url="fake_host_url",
        )

        provision_webauthn_obj = pretend.stub(
            validate=lambda: False,
            errors=pretend.stub(
                values=pretend.call_recorder(lambda: [["Not a real error"]])
            ),
        )
        provision_webauthn_cls = pretend.call_recorder(
            lambda *a, **kw: provision_webauthn_obj
        )
        monkeypatch.setattr(views, "ProvisionWebAuthnForm", provision_webauthn_cls)

        view = views.ProvisionWebAuthnViews(request)
        result = view.validate_webauthn_provision()

        assert request.session.get_webauthn_challenge.calls == [pretend.call()]
        assert request.session.clear_webauthn_challenge.calls == [pretend.call()]
        assert user_service.add_webauthn.calls == []
        assert result == {"fail": {"errors": ["Not a real error"]}}

    def test_delete_webauthn(self, monkeypatch):
        user_service = pretend.stub()
        request = pretend.stub(
            POST={},
            user=pretend.stub(
                id=1234,
                username=pretend.stub(),
                webauthn=pretend.stub(
                    __get__=pretend.call_recorder(lambda *a: [pretend.stub]),
                    __len__=pretend.call_recorder(lambda *a: 1),
                    remove=pretend.call_recorder(lambda *a: pretend.stub()),
                ),
                record_event=pretend.call_recorder(lambda *a, **kw: None),
                has_single_2fa=False,
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=pretend.call_recorder(lambda x: "/foo/bar"),
            find_service=lambda *a, **kw: user_service,
            remote_addr="0.0.0.0",
        )

        delete_webauthn_obj = pretend.stub(
            validate=lambda: True,
            webauthn=pretend.stub(),
            label=pretend.stub(data="fake label"),
        )
        delete_webauthn_cls = pretend.call_recorder(
            lambda *a, **kw: delete_webauthn_obj
        )
        monkeypatch.setattr(views, "DeleteWebAuthnForm", delete_webauthn_cls)

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_two_factor_removed_email", send_email)

        view = views.ProvisionWebAuthnViews(request)
        result = view.delete_webauthn()

        assert request.session.flash.calls == [
            pretend.call("Security device removed", queue="success")
        ]
        assert request.route_path.calls == [pretend.call("manage.account")]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar"
        assert request.user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.TwoFactorMethodRemoved,
                request=request,
                additional={
                    "method": "webauthn",
                    "label": delete_webauthn_obj.label.data,
                },
            )
        ]
        assert send_email.calls == [
            pretend.call(request, request.user, method="webauthn"),
        ]

    def test_delete_webauthn_not_provisioned(self):
        request = pretend.stub(
            user=pretend.stub(id=1234, webauthn=[]),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=pretend.call_recorder(lambda x: "/foo/bar"),
            find_service=lambda *a, **kw: pretend.stub(),
        )

        view = views.ProvisionWebAuthnViews(request)
        result = view.delete_webauthn()

        assert request.session.flash.calls == [
            pretend.call("There is no security device to delete", queue="error")
        ]
        assert request.route_path.calls == [pretend.call("manage.account")]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar"

    def test_delete_webauthn_invalid_form(self, monkeypatch):
        request = pretend.stub(
            POST={},
            user=pretend.stub(
                id=1234,
                username=pretend.stub(),
                webauthn=[pretend.stub()],
                has_single_2fa=False,
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=pretend.call_recorder(lambda x: "/foo/bar"),
            find_service=lambda *a, **kw: pretend.stub(),
        )

        delete_webauthn_obj = pretend.stub(validate=lambda: False)
        delete_webauthn_cls = pretend.call_recorder(
            lambda *a, **kw: delete_webauthn_obj
        )
        monkeypatch.setattr(views, "DeleteWebAuthnForm", delete_webauthn_cls)

        view = views.ProvisionWebAuthnViews(request)
        result = view.delete_webauthn()

        assert request.session.flash.calls == [
            pretend.call("Invalid credentials", queue="error")
        ]
        assert request.route_path.calls == [pretend.call("manage.account")]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar"

    def test_delete_webauthn_last_2fa(self):
        request = pretend.stub(
            user=pretend.stub(id=1234, webauthn=[pretend.stub()], has_single_2fa=True),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=pretend.call_recorder(lambda x: "/foo/bar"),
            find_service=lambda *a, **kw: pretend.stub(),
        )

        view = views.ProvisionWebAuthnViews(request)
        result = view.delete_webauthn()

        assert request.session.flash.calls == [
            pretend.call("Cannot remove last 2FA method", queue="error")
        ]
        assert request.route_path.calls == [pretend.call("manage.account")]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar"


class TestProvisionRecoveryCodes:
    def test_recovery_codes_generate(self, monkeypatch):
        user_service = pretend.stub(
            has_recovery_codes=lambda user_id: False,
            has_two_factor=lambda user_id: True,
            generate_recovery_codes=lambda user_id: ["aaaaaaaaaaaa", "bbbbbbbbbbbb"],
        )
        request = pretend.stub(
            find_service=lambda interface, **kw: {IUserService: user_service}[
                interface
            ],
            user=pretend.stub(
                id=1,
                record_event=pretend.call_recorder(lambda *a, **kw: None),
            ),
            remote_addr="0.0.0.0",
        )

        send_recovery_codes_generated_email = pretend.call_recorder(
            lambda request, user: None
        )
        monkeypatch.setattr(
            views,
            "send_recovery_codes_generated_email",
            send_recovery_codes_generated_email,
        )

        view = views.ProvisionRecoveryCodesViews(request)
        result = view.recovery_codes_generate()

        assert request.user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.RecoveryCodesGenerated,
                request=request,
            )
        ]

        assert result == {"recovery_codes": ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]}
        assert send_recovery_codes_generated_email.calls == [
            pretend.call(request, request.user)
        ]

    def test_recovery_codes_generate_already_exist(self, pyramid_request):
        user_service = pretend.stub(
            has_two_factor=lambda user_id: True, has_recovery_codes=lambda user_id: True
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )
        pyramid_request.find_service = lambda interface, **kw: {
            IUserService: user_service
        }[interface]
        pyramid_request.user = pretend.stub(id=pretend.stub())
        pyramid_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the/route"
        )

        view = views.ProvisionRecoveryCodesViews(pyramid_request)
        result = view.recovery_codes_generate()

        assert result == {
            "recovery_codes": None,
            "_error": "Recovery codes already generated",
            "_message": (
                "Generating new recovery codes will invalidate your existing codes."
            ),
        }

    def test_recovery_codes_regenerate(self, monkeypatch):
        confirm_password_cls = pretend.call_recorder(
            lambda *a, **kw: pretend.stub(validate=lambda: True)
        )
        monkeypatch.setattr(views, "ConfirmPasswordForm", confirm_password_cls)

        user_service = pretend.stub(
            has_recovery_codes=lambda user_id: True,
            has_two_factor=lambda user_id: True,
            generate_recovery_codes=lambda user_id: ["cccccccccccc", "dddddddddddd"],
        )
        request = pretend.stub(
            POST={"confirm_password": "correct password"},
            find_service=lambda interface, **kw: {IUserService: user_service}[
                interface
            ],
            user=pretend.stub(
                id=1,
                username="username",
                record_event=pretend.call_recorder(lambda *a, **kw: None),
            ),
            remote_addr="0.0.0.0",
        )
        send_recovery_codes_generated_email = pretend.call_recorder(
            lambda request, user: None
        )
        monkeypatch.setattr(
            views,
            "send_recovery_codes_generated_email",
            send_recovery_codes_generated_email,
        )

        view = views.ProvisionRecoveryCodesViews(request)
        result = view.recovery_codes_regenerate()

        assert request.user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.RecoveryCodesRegenerated,
                request=request,
            )
        ]

        assert result == {"recovery_codes": ["cccccccccccc", "dddddddddddd"]}
        assert send_recovery_codes_generated_email.calls == [
            pretend.call(request, request.user)
        ]

    def test_recovery_codes_burn_get(self):
        form = pretend.stub()
        recovery_code_form_cls = pretend.call_recorder(lambda *a, **kw: form)
        user = pretend.stub(
            id=pretend.stub(),
            has_recovery_codes=True,
            has_burned_recovery_codes=False,
        )
        request = pretend.stub(
            method="GET",
            POST={},
            user=user,
            find_service=lambda *a, **kw: pretend.stub(get_user=lambda *a: user),
        )

        view = views.ProvisionRecoveryCodesViews(request)
        result = view.recovery_codes_burn(_form_class=recovery_code_form_cls)

        assert result == {"form": form}

    def test_recovery_codes_burn_post(self):
        form = pretend.stub(validate=pretend.call_recorder(lambda: True))
        recovery_code_form_cls = pretend.call_recorder(lambda *a, **kw: form)
        user = pretend.stub(
            id=pretend.stub(),
            has_recovery_codes=True,
            has_burned_recovery_codes=False,
        )
        request = pretend.stub(
            method="POST",
            POST={},
            _=lambda a: a,
            user=user,
            find_service=lambda *a, **kw: pretend.stub(get_user=lambda *a: user),
            route_path=pretend.call_recorder(lambda x: "/foo/bar"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )

        view = views.ProvisionRecoveryCodesViews(request)
        result = view.recovery_codes_burn(_form_class=recovery_code_form_cls)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/foo/bar"

        assert request.route_path.calls == [pretend.call("manage.account.two-factor")]
        assert form.validate.calls == [pretend.call()]
        assert request.session.flash.calls == [
            pretend.call(
                "Recovery code accepted. The supplied code cannot be used again.",
                queue="success",
            )
        ]

    @pytest.mark.parametrize(
        ("user", "expected"),
        [
            (
                pretend.stub(
                    id=pretend.stub(),
                    has_recovery_codes=False,
                ),
                "manage.account",
            ),
            (
                pretend.stub(
                    id=pretend.stub(),
                    has_recovery_codes=True,
                    has_burned_recovery_codes=True,
                ),
                "manage.account.two-factor",
            ),
        ],
    )
    def test_recovery_codes_burn_redirect(self, user, expected):
        request = pretend.stub(
            user=user,
            find_service=lambda *a, **kw: pretend.stub(get_user=lambda *a: user),
            route_path=pretend.call_recorder(lambda x: "/foo/bar"),
        )

        view = views.ProvisionRecoveryCodesViews(request)
        result = view.recovery_codes_burn()

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/foo/bar"


class TestProvisionMacaroonViews:
    def test_default_response(self, monkeypatch):
        create_macaroon_obj = pretend.stub()
        create_macaroon_cls = pretend.call_recorder(
            lambda *a, **kw: create_macaroon_obj
        )
        monkeypatch.setattr(views, "CreateMacaroonForm", create_macaroon_cls)

        delete_macaroon_obj = pretend.stub()
        delete_macaroon_cls = pretend.call_recorder(
            lambda *a, **kw: delete_macaroon_obj
        )
        monkeypatch.setattr(views, "DeleteMacaroonForm", delete_macaroon_cls)

        project_names = [pretend.stub()]
        monkeypatch.setattr(
            views.ProvisionMacaroonViews, "project_names", project_names
        )

        request = pretend.stub(
            user=pretend.stub(id=pretend.stub(), username=pretend.stub()),
            find_service=lambda interface, **kw: {
                IMacaroonService: pretend.stub(),
                IUserService: pretend.stub(),
            }[interface],
        )

        view = views.ProvisionMacaroonViews(request)

        assert view.default_response == {
            "project_names": project_names,
            "create_macaroon_form": create_macaroon_obj,
            "delete_macaroon_form": delete_macaroon_obj,
        }

    def test_project_names(self, db_request):
        user = UserFactory.create()
        another_user = UserFactory.create()

        db_request.user = user
        db_request.find_service = lambda *a, **kw: pretend.stub()

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

    def test_manage_macaroons(self, monkeypatch):
        request = pretend.stub(
            find_service=lambda *a, **kw: pretend.stub(),
            params=pretend.stub(get=lambda s: pretend.stub()),
        )

        default_response = {"default": "response"}
        monkeypatch.setattr(
            views.ProvisionMacaroonViews, "default_response", default_response
        )
        view = views.ProvisionMacaroonViews(request)
        result = view.manage_macaroons()

        assert result == default_response

    def test_create_macaroon_not_allowed(self, pyramid_request):
        pyramid_request.route_path = pretend.call_recorder(lambda x: "/foo/bar")
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        pyramid_request.user = pretend.stub(has_primary_verified_email=False)
        pyramid_request.find_service = lambda interface, **kw: pretend.stub()

        view = views.ProvisionMacaroonViews(pyramid_request)
        result = view.create_macaroon()

        assert pyramid_request.route_path.calls == [pretend.call("manage.account")]
        assert pyramid_request.session.flash.calls == [
            pretend.call("Verify your email to create an API token.", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/foo/bar"

    def test_create_macaroon_invalid_form(self, monkeypatch):
        macaroon_service = pretend.stub(
            create_macaroon=pretend.call_recorder(lambda *a, **kw: pretend.stub())
        )
        request = pretend.stub(
            POST={},
            user=pretend.stub(id=pretend.stub(), has_primary_verified_email=True),
            find_service=lambda interface, **kw: {
                IMacaroonService: macaroon_service,
                IUserService: pretend.stub(),
            }[interface],
        )

        create_macaroon_obj = pretend.stub(validate=lambda: False)
        create_macaroon_cls = pretend.call_recorder(
            lambda *a, **kw: create_macaroon_obj
        )
        monkeypatch.setattr(views, "CreateMacaroonForm", create_macaroon_cls)

        project_names = [pretend.stub()]
        monkeypatch.setattr(
            views.ProvisionMacaroonViews, "project_names", project_names
        )

        default_response = {"default": "response"}
        monkeypatch.setattr(
            views.ProvisionMacaroonViews, "default_response", default_response
        )

        view = views.ProvisionMacaroonViews(request)
        result = view.create_macaroon()

        assert result == {
            **default_response,
            "create_macaroon_form": create_macaroon_obj,
        }
        assert macaroon_service.create_macaroon.calls == []

    @pytest.mark.parametrize("has_2fa", [True, False])
    def test_create_macaroon(self, monkeypatch, has_2fa):
        macaroon = pretend.stub()
        macaroon_service = pretend.stub(
            create_macaroon=pretend.call_recorder(
                lambda *a, **kw: ("not a real raw macaroon", macaroon)
            )
        )
        user_service = pretend.stub()
        request = pretend.stub(
            POST={},
            domain=pretend.stub(),
            user=pretend.stub(
                id="a user id",
                has_primary_verified_email=True,
                record_event=pretend.call_recorder(lambda *a, **kw: None),
                has_two_factor=has_2fa,
            ),
            find_service=lambda interface, **kw: {
                IMacaroonService: macaroon_service,
                IUserService: user_service,
            }[interface],
            remote_addr="0.0.0.0",
        )

        create_macaroon_obj = pretend.stub(
            validate=lambda: True,
            description=pretend.stub(data=pretend.stub()),
            validated_scope="user",
        )
        create_macaroon_cls = pretend.call_recorder(
            lambda *a, **kw: create_macaroon_obj
        )
        monkeypatch.setattr(views, "CreateMacaroonForm", create_macaroon_cls)

        project_names = [pretend.stub()]
        monkeypatch.setattr(
            views.ProvisionMacaroonViews, "project_names", project_names
        )

        default_response = {"default": "response"}
        monkeypatch.setattr(
            views.ProvisionMacaroonViews, "default_response", default_response
        )

        view = views.ProvisionMacaroonViews(request)
        result = view.create_macaroon()

        assert macaroon_service.create_macaroon.calls == [
            pretend.call(
                location=request.domain,
                user_id=request.user.id,
                description=create_macaroon_obj.description.data,
                scopes=[
                    caveats.RequestUser(user_id="a user id"),
                ],
                additional={"made_with_2fa": has_2fa},
            )
        ]
        assert result == {
            **default_response,
            "serialized_macaroon": "not a real raw macaroon",
            "macaroon": macaroon,
            "create_macaroon_form": create_macaroon_obj,
        }
        assert request.user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.APITokenAdded,
                request=request,
                additional={
                    "description": create_macaroon_obj.description.data,
                    "caveats": [
                        {
                            "permissions": create_macaroon_obj.validated_scope,
                            "version": 1,
                        }
                    ],
                },
            )
        ]

    def test_create_macaroon_records_events_for_each_project(self, monkeypatch):
        macaroon = pretend.stub()
        macaroon_service = pretend.stub(
            create_macaroon=pretend.call_recorder(
                lambda *a, **kw: ("not a real raw macaroon", macaroon)
            )
        )
        record_project_event = pretend.call_recorder(lambda *a, **kw: None)
        user_service = pretend.stub()
        request = pretend.stub(
            POST={},
            domain=pretend.stub(),
            user=pretend.stub(
                id=pretend.stub(),
                has_primary_verified_email=True,
                username=pretend.stub(),
                has_two_factor=False,
                projects=[
                    pretend.stub(
                        id=uuid.uuid4(),
                        normalized_name="foo",
                        record_event=record_project_event,
                    ),
                    pretend.stub(
                        id=uuid.uuid4(),
                        normalized_name="bar",
                        record_event=record_project_event,
                    ),
                ],
                record_event=pretend.call_recorder(lambda *a, **kw: None),
            ),
            find_service=lambda interface, **kw: {
                IMacaroonService: macaroon_service,
                IUserService: user_service,
            }[interface],
            remote_addr="0.0.0.0",
        )

        create_macaroon_obj = pretend.stub(
            validate=lambda: True,
            description=pretend.stub(data=pretend.stub()),
            validated_scope={"projects": ["foo", "bar"]},
        )
        create_macaroon_cls = pretend.call_recorder(
            lambda *a, **kw: create_macaroon_obj
        )
        monkeypatch.setattr(views, "CreateMacaroonForm", create_macaroon_cls)

        project_names = [pretend.stub()]
        monkeypatch.setattr(
            views.ProvisionMacaroonViews, "project_names", project_names
        )

        default_response = {"default": "response"}
        monkeypatch.setattr(
            views.ProvisionMacaroonViews, "default_response", default_response
        )

        view = views.ProvisionMacaroonViews(request)
        result = view.create_macaroon()

        assert macaroon_service.create_macaroon.calls == [
            pretend.call(
                location=request.domain,
                user_id=request.user.id,
                description=create_macaroon_obj.description.data,
                scopes=[
                    caveats.ProjectName(normalized_names=["foo", "bar"]),
                    caveats.ProjectID(
                        project_ids=[str(p.id) for p in request.user.projects]
                    ),
                ],
                additional={"made_with_2fa": False},
            )
        ]
        assert result == {
            **default_response,
            "serialized_macaroon": "not a real raw macaroon",
            "macaroon": macaroon,
            "create_macaroon_form": create_macaroon_obj,
        }
        assert request.user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.APITokenAdded,
                request=request,
                additional={
                    "description": create_macaroon_obj.description.data,
                    "caveats": [
                        {
                            "permissions": create_macaroon_obj.validated_scope,
                            "version": 1,
                        },
                        {"project_ids": [str(p.id) for p in request.user.projects]},
                    ],
                },
            )
        ]
        assert record_project_event.calls == [
            pretend.call(
                tag=EventTag.Project.APITokenAdded,
                request=request,
                additional={
                    "description": create_macaroon_obj.description.data,
                    "user": request.user.username,
                },
            ),
            pretend.call(
                tag=EventTag.Project.APITokenAdded,
                request=request,
                additional={
                    "description": create_macaroon_obj.description.data,
                    "user": request.user.username,
                },
            ),
        ]

    def test_delete_macaroon_invalid_form(self, monkeypatch, pyramid_request):
        macaroon_service = pretend.stub(
            delete_macaroon=pretend.call_recorder(lambda id: pretend.stub())
        )
        pyramid_request.POST = {
            "confirm_password": "password",
            "macaroon_id": "macaroon_id",
        }
        pyramid_request.route_path = pretend.call_recorder(lambda x: pretend.stub())
        pyramid_request.find_service = lambda interface, **kw: {
            IMacaroonService: macaroon_service,
            IUserService: pretend.stub(),
        }[interface]
        pyramid_request.referer = "/fake/safe/route"
        pyramid_request.host = None
        pyramid_request.user = pretend.stub(username=pretend.stub())
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        delete_macaroon_obj = pretend.stub(validate=lambda: False)
        delete_macaroon_cls = pretend.call_recorder(
            lambda *a, **kw: delete_macaroon_obj
        )
        monkeypatch.setattr(views, "DeleteMacaroonForm", delete_macaroon_cls)

        view = views.ProvisionMacaroonViews(pyramid_request)
        result = view.delete_macaroon()

        assert pyramid_request.route_path.calls == []
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/fake/safe/route"
        assert macaroon_service.delete_macaroon.calls == []
        assert pyramid_request.session.flash.calls == [
            pretend.call("Invalid credentials. Try again", queue="error")
        ]

    def test_delete_macaroon_dangerous_redirect(self, monkeypatch, pyramid_request):
        macaroon_service = pretend.stub(
            delete_macaroon=pretend.call_recorder(lambda id: pretend.stub())
        )
        pyramid_request.POST = {
            "confirm_password": "password",
            "macaroon_id": "macaroon_id",
        }
        pyramid_request.route_path = pretend.call_recorder(lambda x: "/safe/route")
        pyramid_request.find_service = lambda interface, **kw: {
            IMacaroonService: macaroon_service,
            IUserService: pretend.stub(),
        }[interface]
        pyramid_request.referer = "http://google.com/"
        pyramid_request.host = None
        pyramid_request.user = pretend.stub(username=pretend.stub())
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        delete_macaroon_obj = pretend.stub(validate=lambda: False)
        delete_macaroon_cls = pretend.call_recorder(
            lambda *a, **kw: delete_macaroon_obj
        )
        monkeypatch.setattr(views, "DeleteMacaroonForm", delete_macaroon_cls)

        view = views.ProvisionMacaroonViews(pyramid_request)
        result = view.delete_macaroon()

        assert pyramid_request.route_path.calls == [pretend.call("manage.account")]
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/safe/route"
        assert macaroon_service.delete_macaroon.calls == []

    def test_delete_macaroon(self, monkeypatch, pyramid_request):
        macaroon = pretend.stub(description="fake macaroon", permissions_caveat="user")
        macaroon_service = pretend.stub(
            delete_macaroon=pretend.call_recorder(lambda id: pretend.stub()),
            find_macaroon=pretend.call_recorder(lambda id: macaroon),
        )
        user_service = pretend.stub()
        pyramid_request.POST = {
            "confirm_password": "password",
            "macaroon_id": "macaroon_id",
        }
        pyramid_request.route_path = pretend.call_recorder(lambda x: pretend.stub())
        pyramid_request.find_service = lambda interface, **kw: {
            IMacaroonService: macaroon_service,
            IUserService: user_service,
        }[interface]
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        pyramid_request.referer = "/fake/safe/route"
        pyramid_request.host = None
        pyramid_request.user = pretend.stub(
            id=pretend.stub(),
            username=pretend.stub(),
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )

        delete_macaroon_obj = pretend.stub(
            validate=lambda: True, macaroon_id=pretend.stub(data=pretend.stub())
        )
        delete_macaroon_cls = pretend.call_recorder(
            lambda *a, **kw: delete_macaroon_obj
        )
        monkeypatch.setattr(views, "DeleteMacaroonForm", delete_macaroon_cls)

        view = views.ProvisionMacaroonViews(pyramid_request)
        result = view.delete_macaroon()

        assert pyramid_request.route_path.calls == []
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/fake/safe/route"
        assert macaroon_service.delete_macaroon.calls == [
            pretend.call(delete_macaroon_obj.macaroon_id.data)
        ]
        assert macaroon_service.find_macaroon.calls == [
            pretend.call(delete_macaroon_obj.macaroon_id.data)
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call("Deleted API token 'fake macaroon'.", queue="success")
        ]
        assert pyramid_request.user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.APITokenRemoved,
                request=pyramid_request,
                additional={"macaroon_id": delete_macaroon_obj.macaroon_id.data},
            )
        ]

    def test_delete_macaroon_when_non_existent(self, monkeypatch, pyramid_request):
        user_service = pretend.stub()
        macaroon_service = pretend.stub(
            delete_macaroon=pretend.call_recorder(lambda id: pretend.stub()),
            find_macaroon=pretend.call_recorder(lambda id: None),
        )
        delete_macaroon_obj = pretend.stub(
            validate=lambda: True, macaroon_id=pretend.stub(data=pretend.stub())
        )
        delete_macaroon_cls = pretend.call_recorder(
            lambda *a, **kw: delete_macaroon_obj
        )
        monkeypatch.setattr(views, "DeleteMacaroonForm", delete_macaroon_cls)

        pyramid_request.POST = {
            "confirm_password": "password",
            "macaroon_id": "macaroon_id",
        }
        pyramid_request.find_service = lambda interface, **kw: {
            IMacaroonService: macaroon_service,
            IUserService: user_service,
        }[interface]
        pyramid_request.route_path = pretend.call_recorder(lambda x: "/manage/account/")
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        pyramid_request.user = pretend.stub(
            id=pretend.stub(),
            username=pretend.stub(),
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )

        view = views.ProvisionMacaroonViews(pyramid_request)
        result = view.delete_macaroon()

        assert pyramid_request.route_path.calls == [pretend.call("manage.account")]
        assert isinstance(result, HTTPSeeOther)
        assert macaroon_service.find_macaroon.calls == [
            pretend.call(delete_macaroon_obj.macaroon_id.data)
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call("API Token does not exist.", queue="warning")
        ]

    def test_delete_macaroon_records_events_for_each_project(
        self, monkeypatch, pyramid_request
    ):
        macaroon = pretend.stub(
            description="fake macaroon",
            permissions_caveat={"projects": ["foo", "bar"]},
        )
        macaroon_service = pretend.stub(
            delete_macaroon=pretend.call_recorder(lambda id: pretend.stub()),
            find_macaroon=pretend.call_recorder(lambda id: macaroon),
        )
        record_project_event = pretend.call_recorder(lambda *a, **kw: None)
        user_service = pretend.stub()
        pyramid_request.POST = {
            "confirm_password": pretend.stub(),
            "macaroon_id": pretend.stub(),
        }
        pyramid_request.route_path = pretend.call_recorder(lambda x: pretend.stub())
        pyramid_request.find_service = lambda interface, **kw: {
            IMacaroonService: macaroon_service,
            IUserService: user_service,
        }[interface]
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        pyramid_request.referer = "/fake/safe/route"
        pyramid_request.host = None
        pyramid_request.user = pretend.stub(
            id=pretend.stub(),
            username=pretend.stub(),
            projects=[
                pretend.stub(normalized_name="foo", record_event=record_project_event),
                pretend.stub(normalized_name="bar", record_event=record_project_event),
            ],
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )

        delete_macaroon_obj = pretend.stub(
            validate=lambda: True, macaroon_id=pretend.stub(data=pretend.stub())
        )
        delete_macaroon_cls = pretend.call_recorder(
            lambda *a, **kw: delete_macaroon_obj
        )
        monkeypatch.setattr(views, "DeleteMacaroonForm", delete_macaroon_cls)

        view = views.ProvisionMacaroonViews(pyramid_request)
        result = view.delete_macaroon()

        assert pyramid_request.route_path.calls == []
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/fake/safe/route"
        assert macaroon_service.delete_macaroon.calls == [
            pretend.call(delete_macaroon_obj.macaroon_id.data)
        ]
        assert macaroon_service.find_macaroon.calls == [
            pretend.call(delete_macaroon_obj.macaroon_id.data)
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call("Deleted API token 'fake macaroon'.", queue="success")
        ]
        assert pyramid_request.user.record_event.calls == [
            pretend.call(
                request=pyramid_request,
                tag=EventTag.Account.APITokenRemoved,
                additional={"macaroon_id": delete_macaroon_obj.macaroon_id.data},
            )
        ]
        assert record_project_event.calls == [
            pretend.call(
                tag=EventTag.Project.APITokenRemoved,
                request=pyramid_request,
                additional={
                    "description": "fake macaroon",
                    "user": pyramid_request.user.username,
                },
            ),
            pretend.call(
                tag=EventTag.Project.APITokenRemoved,
                request=pyramid_request,
                additional={
                    "description": "fake macaroon",
                    "user": pyramid_request.user.username,
                },
            ),
        ]


class TestManageProjects:
    def test_manage_projects(self, db_request):
        older_release = ReleaseFactory(created=datetime.datetime(2015, 1, 1))
        project_with_older_release = ProjectFactory(releases=[older_release])
        newer_release = ReleaseFactory(created=datetime.datetime(2017, 1, 1))
        project_with_newer_release = ProjectFactory(releases=[newer_release])
        older_project_with_no_releases = ProjectFactory(
            releases=[], created=datetime.datetime(2016, 1, 1)
        )
        newer_project_with_no_releases = ProjectFactory(
            releases=[], created=datetime.datetime(2018, 1, 1)
        )
        team_project = ProjectFactory(
            name="team-proj", releases=[], created=datetime.datetime(2022, 3, 3)
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
            "projects": [
                team_project,
                newer_project_with_no_releases,
                project_with_newer_release,
                older_project_with_no_releases,
                project_with_older_release,
            ],
            "projects_owned": {
                project_with_newer_release.name,
                newer_project_with_no_releases.name,
            },
            "projects_sole_owned": {
                newer_project_with_no_releases.name,
            },
            "project_invites": [],
        }


class TestManageProjectSettings:
    @pytest.mark.parametrize("enabled", [False, True])
    def test_manage_project_settings(self, enabled, monkeypatch):
        request = pretend.stub(organization_access=enabled)
        project = pretend.stub(organization=None, lifecycle_status=None)
        view = views.ManageProjectSettingsViews(project, request)
        form = pretend.stub()
        view.transfer_organization_project_form_class = lambda *a, **kw: form
        view.add_alternate_repository_form_class = lambda *a, **kw: form

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
            "add_alternate_repository_form_class": form,
        }

    def test_manage_project_settings_in_organization_managed(self, monkeypatch):
        request = pretend.stub(organization_access=True)
        organization_managed = pretend.stub(name="managed-org", is_active=True)
        organization_owned = pretend.stub(name="owned-org", is_active=True)
        project = pretend.stub(organization=organization_managed, lifecycle_status=None)
        view = views.ManageProjectSettingsViews(project, request)
        form = pretend.stub()
        view.transfer_organization_project_form_class = pretend.call_recorder(
            lambda *a, **kw: form
        )
        view.add_alternate_repository_form_class = lambda *a, **kw: form

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
            "add_alternate_repository_form_class": form,
        }
        assert view.transfer_organization_project_form_class.calls == [
            pretend.call(organization_choices={organization_owned})
        ]

    def test_manage_project_settings_in_organization_owned(self, monkeypatch):
        request = pretend.stub(organization_access=True)
        organization_managed = pretend.stub(name="managed-org", is_active=True)
        organization_owned = pretend.stub(name="owned-org", is_active=True)
        project = pretend.stub(organization=organization_owned, lifecycle_status=None)
        view = views.ManageProjectSettingsViews(project, request)
        form = pretend.stub()
        view.transfer_organization_project_form_class = pretend.call_recorder(
            lambda *a, **kw: form
        )
        view.add_alternate_repository_form_class = lambda *a, **kw: form

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
            "add_alternate_repository_form_class": form,
        }
        assert view.transfer_organization_project_form_class.calls == [
            pretend.call(organization_choices={organization_managed})
        ]

    def test_add_alternate_repository(self, monkeypatch, db_request):
        project = ProjectFactory.create(name="foo")

        db_request.POST = MultiDict(
            {
                "display_name": "foo alt repo",
                "link_url": "https://example.org",
                "description": "foo alt repo descr",
                "alternate_repository_location": "add",
            }
        )
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        add_alternate_repository_form_class = pretend.call_recorder(
            views.AddAlternateRepositoryForm
        )
        monkeypatch.setattr(
            views,
            "AddAlternateRepositoryForm",
            add_alternate_repository_form_class,
        )

        settings_views = views.ManageProjectSettingsViews(project, db_request)
        result = settings_views.add_project_alternate_repository()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert db_request.session.flash.calls == [
            pretend.call("Added alternate repository 'foo alt repo'", queue="success")
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]
        assert add_alternate_repository_form_class.calls == [
            pretend.call(db_request.POST)
        ]

    def test_add_alternate_repository_invalid(self, monkeypatch, db_request):
        project = ProjectFactory.create(name="foo")

        db_request.POST = MultiDict(
            {
                "display_name": "foo alt repo",
                "link_url": "invalid link",
                "description": "foo alt repo descr",
                "alternate_repository_location": "add",
            }
        )
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        add_alternate_repository_form_class = pretend.call_recorder(
            views.AddAlternateRepositoryForm
        )
        monkeypatch.setattr(
            views,
            "AddAlternateRepositoryForm",
            add_alternate_repository_form_class,
        )

        settings_views = views.ManageProjectSettingsViews(project, db_request)
        result = settings_views.add_project_alternate_repository()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert db_request.session.flash.calls == [
            pretend.call("Invalid alternate repository location details", queue="error")
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]
        assert add_alternate_repository_form_class.calls == [
            pretend.call(db_request.POST)
        ]

    def test_delete_alternate_repository(self, db_request):
        project = ProjectFactory.create(name="foo")
        alt_repo = AlternateRepositoryFactory.create(project=project)

        db_request.POST = MultiDict(
            {
                "alternate_repository_id": str(alt_repo.id),
                "confirm_alternate_repository_name": alt_repo.name,
                "alternate_repository_location": "delete",
            }
        )
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        settings_views = views.ManageProjectSettingsViews(project, db_request)
        result = settings_views.delete_project_alternate_repository()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Deleted alternate repository '{alt_repo.name}'", queue="success"
            )
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]

    @pytest.mark.parametrize("alt_repo_id", [None, "", "blah"])
    def test_delete_alternate_repository_invalid_id(self, db_request, alt_repo_id):
        project = ProjectFactory.create(name="foo")
        alt_repo = AlternateRepositoryFactory.create(project=project)

        db_request.POST = MultiDict(
            {
                "alternate_repository_id": alt_repo_id,
                "confirm_alternate_repository_name": alt_repo.name,
                "alternate_repository_location": "delete",
            }
        )
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        settings_views = views.ManageProjectSettingsViews(project, db_request)
        result = settings_views.delete_project_alternate_repository()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert db_request.session.flash.calls == [
            pretend.call("Invalid alternate repository id", queue="error")
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]

    def test_delete_alternate_repository_wrong_id(self, db_request):
        project = ProjectFactory.create(name="foo")
        alt_repo = AlternateRepositoryFactory.create(project=project)

        db_request.POST = MultiDict(
            {
                "alternate_repository_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "confirm_alternate_repository_name": alt_repo.name,
                "alternate_repository_location": "delete",
            }
        )
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        settings_views = views.ManageProjectSettingsViews(project, db_request)
        result = settings_views.delete_project_alternate_repository()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert db_request.session.flash.calls == [
            pretend.call("Invalid alternate repository for project", queue="error")
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]

    def test_delete_alternate_repository_no_confirm(self, db_request):
        project = ProjectFactory.create(name="foo")
        alt_repo = AlternateRepositoryFactory.create(project=project)

        db_request.POST = MultiDict(
            {
                "alternate_repository_id": str(alt_repo.id),
                "alternate_repository_location": "delete",
            }
        )
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        settings_views = views.ManageProjectSettingsViews(project, db_request)
        result = settings_views.delete_project_alternate_repository()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert db_request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]

    def test_delete_alternate_repository_wrong_confirm(self, db_request):
        project = ProjectFactory.create(name="foo")
        alt_repo = AlternateRepositoryFactory.create(project=project)

        db_request.POST = MultiDict(
            {
                "alternate_repository_id": str(alt_repo.id),
                "confirm_alternate_repository_name": f"invalid-confirm-{alt_repo.name}",
                "alternate_repository_location": "delete",
            }
        )
        db_request.flags = pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = UserFactory.create()

        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        settings_views = views.ManageProjectSettingsViews(project, db_request)
        result = settings_views.delete_project_alternate_repository()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Could not delete alternate repository - "
                f"invalid-confirm-{alt_repo.name} is not the same as {alt_repo.name}",
                queue="error",
            )
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
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
            organization_access=True,
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
            organization_access=True,
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=lambda *a, **kw: "/foo/bar/",
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

    def test_remove_organization_project_disable_organizations(self):
        project = pretend.stub(name="foo", normalized_name="foo")
        request = pretend.stub(
            organization_access=False,
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )

        result = org_views.remove_organization_project(project, request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert request.session.flash.calls == [
            pretend.call("Organizations are disabled", queue="error")
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
            organization_access=True,
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
            ),
        ]

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
            organization_access=True,
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
            organization_access=True,
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

    def test_transfer_organization_project_disable_organizations(self):
        project = pretend.stub(name="foo", normalized_name="foo")
        request = pretend.stub(
            organization_access=False,
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )

        result = org_views.transfer_organization_project(project, request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert request.session.flash.calls == [
            pretend.call("Organizations are disabled", queue="error")
        ]

        assert request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
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
            org_views,
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
            organization_access=True,
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
            org_views,
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
            )
        ]
        assert send_organization_project_added_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=organization.name,
                project_name=project.name,
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
            org_views,
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
            )
        ]
        assert send_organization_project_added_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=organization.name,
                project_name=project.name,
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
            org_views,
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
            )
        ]
        assert send_organization_project_added_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=organization.name,
                project_name=project.name,
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
                    "See https://pypi.org/help#admin-intervention for details."
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

    def test_delete_project_release_disallow_deletion(
        self, monkeypatch, pyramid_request
    ):
        release = pretend.stub(
            version="1.2.3",
            canonical_version="1.2.3",
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
                    "See https://pypi.org/help#admin-intervention for details."
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
                + f"'invalid' is not the same as {release.version!r}",
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
                + f"'invalid' is not the same as {release.version!r}",
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

        db_request.POST = {"confirm_delete_version": release.version}
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
        release = pretend.stub(version="1.2.3", project=pretend.stub(name="foobar"))
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
        release = pretend.stub(version="1.2.3", project=pretend.stub(name="foobar"))
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
                + f"'invalid' is not the same as {release.version!r}",
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

    def test_delete_project_release_file_disallow_deletion(self, pyramid_request):
        release = pretend.stub(version="1.2.3", project=pretend.stub(name="foobar"))
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
                    "See https://pypi.org/help#admin-intervention for details."
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
                + f"'invalid' is not the same as {release.project.name!r}",
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


class TestManageProjectRoles:
    @pytest.fixture
    def organization(self, _enable_organizations, pyramid_user):
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

    def test_token_expired(self, db_request, token_service):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        RoleInvitationFactory.create(user=user, project=project)
        owner_user = UserFactory.create()
        RoleFactory(user=owner_user, project=project, role_name="Owner")

        user_service = pretend.stub(get_user=lambda userid: user)
        token_service.loads = pretend.call_recorder(pretend.raiser(TokenExpired))
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
            lambda *a, **kw: "/manage/projects/roles"
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
            pretend.call("Invitation already expired.", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/projects/roles"


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
                time=datetime.datetime(2018, 2, 5, 17, 18, 18, 462_634),
                additional={
                    "project_id": str(project.id),
                },
            ),
            ProjectEventFactory.create(
                source=project,
                tag="fake:event",
                time=datetime.datetime(2017, 2, 5, 17, 18, 18, 462_634),
            ),
            ProjectEventFactory.create(
                source=project,
                tag="fake:event",
                time=datetime.datetime(2019, 2, 5, 17, 18, 18, 462_634),
            ),
            FileEventFactory.create(
                source=file_,
                tag="fake:event",
                time=datetime.datetime(2016, 2, 5, 17, 18, 18, 462_634),
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
            .filter(File.Event.additional["project_id"].astext == str(project.id))
        )
        events_query = project_events_query.union(file_events_query).order_by(
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
            .filter(File.Event.additional["project_id"].astext == str(project.id))
        )
        events_query = project_events_query.union(file_events_query).order_by(
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
            .filter(File.Event.additional["project_id"].astext == str(project.id))
        )
        events_query = project_events_query.union(file_events_query).order_by(
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


class TestManageOIDCPublisherViews:
    def test_initializes(self, metrics):
        project = pretend.stub()
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda *a, **kw: metrics),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                },
            ),
            POST=MultiDict(),
        )
        view = views.ManageOIDCPublisherViews(project, request)

        assert view.project is project
        assert view.request is request
        assert view.metrics is metrics

        assert view.request.find_service.calls == [
            pretend.call(IMetricsService, context=None)
        ]

    @pytest.mark.parametrize(
        ("ip_exceeded", "user_exceeded"),
        [
            (False, False),
            (False, True),
            (True, False),
        ],
    )
    def test_ratelimiting(self, metrics, ip_exceeded, user_exceeded):
        project = pretend.stub()
        user_rate_limiter = pretend.stub(
            hit=pretend.call_recorder(lambda *a, **kw: None),
            test=pretend.call_recorder(lambda uid: not user_exceeded),
            resets_in=pretend.call_recorder(lambda uid: pretend.stub()),
        )
        ip_rate_limiter = pretend.stub(
            hit=pretend.call_recorder(lambda *a, **kw: None),
            test=pretend.call_recorder(lambda ip: not ip_exceeded),
            resets_in=pretend.call_recorder(lambda uid: pretend.stub()),
        )

        def find_service(iface, name=None, context=None):
            if iface is IMetricsService:
                return metrics

            if name == "user_oidc.publisher.register":
                return user_rate_limiter
            else:
                return ip_rate_limiter

        request = pretend.stub(
            find_service=pretend.call_recorder(find_service),
            user=pretend.stub(id=pretend.stub()),
            remote_addr=pretend.stub(),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                },
            ),
            POST=MultiDict(),
        )

        view = views.ManageOIDCPublisherViews(project, request)

        assert view._ratelimiters == {
            "user.oidc": user_rate_limiter,
            "ip.oidc": ip_rate_limiter,
        }
        assert request.find_service.calls == [
            pretend.call(IMetricsService, context=None),
            pretend.call(IRateLimiter, name="user_oidc.publisher.register"),
            pretend.call(IRateLimiter, name="ip_oidc.publisher.register"),
        ]

        view._hit_ratelimits()

        assert user_rate_limiter.hit.calls == [
            pretend.call(request.user.id),
        ]
        assert ip_rate_limiter.hit.calls == [pretend.call(request.remote_addr)]

        if user_exceeded or ip_exceeded:
            with pytest.raises(TooManyOIDCRegistrations):
                view._check_ratelimits()
        else:
            view._check_ratelimits()

    def test_manage_project_oidc_publishers(self, monkeypatch):
        project = pretend.stub(oidc_publishers=[])
        request = pretend.stub(
            user=pretend.stub(),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                },
            ),
            find_service=lambda *a, **kw: None,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            POST=MultiDict(),
        )

        view = views.ManageOIDCPublisherViews(project, request)
        assert view.manage_project_oidc_publishers() == {
            "disabled": {
                "GitHub": False,
                "GitLab": False,
                "Google": False,
                "ActiveState": False,
            },
            "project": project,
            "github_publisher_form": view.github_publisher_form,
            "gitlab_publisher_form": view.gitlab_publisher_form,
            "google_publisher_form": view.google_publisher_form,
            "activestate_publisher_form": view.activestate_publisher_form,
            "prefilled_provider": view.prefilled_provider,
        }

        assert request.flags.disallow_oidc.calls == [
            pretend.call(),
            pretend.call(AdminFlagValue.DISALLOW_GITHUB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GITLAB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GOOGLE_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC),
        ]

    def test_manage_project_oidc_publishers_admin_disabled(
        self, monkeypatch, pyramid_request
    ):
        project = pretend.stub(oidc_publishers=[])
        pyramid_request.user = pretend.stub()
        pyramid_request.registry = pretend.stub(
            settings={
                "github.token": "fake-api-token",
            },
        )
        pyramid_request.find_service = lambda *a, **kw: None
        pyramid_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: True)
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        pyramid_request.POST = MultiDict()

        view = views.ManageOIDCPublisherViews(project, pyramid_request)

        assert view.manage_project_oidc_publishers() == {
            "disabled": {
                "GitHub": True,
                "GitLab": True,
                "Google": True,
                "ActiveState": True,
            },
            "project": project,
            "github_publisher_form": view.github_publisher_form,
            "gitlab_publisher_form": view.gitlab_publisher_form,
            "google_publisher_form": view.google_publisher_form,
            "activestate_publisher_form": view.activestate_publisher_form,
            "prefilled_provider": view.prefilled_provider,
        }

        assert pyramid_request.flags.disallow_oidc.calls == [
            pretend.call(),
            pretend.call(AdminFlagValue.DISALLOW_GITHUB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GITLAB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GOOGLE_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC),
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                (
                    "Trusted publishing is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
        ]

    @pytest.mark.parametrize(
        ("form_name", "prefilled_data"),
        [
            # All fields of GitHub provider
            (
                "github_publisher_form",
                {
                    "provider": "github",
                    "owner": "owner",
                    "repository": "repo",
                    "workflow_filename": "file.yml",
                    "environment": "my_env",
                },
            ),
            # All fields of GitLab provider
            (
                "gitlab_publisher_form",
                {
                    "provider": "gitlab",
                    "namespace": "owner",
                    "project": "repo",
                    "workflow_filepath": "file.yml",
                    "environment": "my_env",
                },
            ),
            # All fields of Google provider
            (
                "google_publisher_form",
                {
                    "provider": "google",
                    "email": "email@example.com",
                    "sub": "my_subject",
                },
            ),
            # All fields of ActiveState provider
            (
                "activestate_publisher_form",
                {
                    "provider": "activestate",
                    "organization": "my_org",
                    "project": "my_project",
                    "actor": "my_actor",
                },
            ),
            # All fields of GitHub provider, case-insensitive
            (
                "github_publisher_form",
                {
                    "provider": "GitHub",
                    "owner": "owner",
                    "repository": "repo",
                    "workflow_filename": "file.yml",
                    "environment": "my_env",
                },
            ),
        ],
    )
    def test_manage_project_oidc_publishers_prefill(
        self, monkeypatch, form_name, prefilled_data
    ):
        project = pretend.stub(oidc_publishers=[])
        request = pretend.stub(
            user=pretend.stub(),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                },
            ),
            find_service=lambda *a, **kw: None,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            POST=MultiDict(),
            params=MultiDict(prefilled_data),
        )

        view = views.ManageOIDCPublisherViews(project, request)
        assert view.manage_project_oidc_publishers_prefill() == {
            "disabled": {
                "GitHub": False,
                "GitLab": False,
                "Google": False,
                "ActiveState": False,
            },
            "project": project,
            "github_publisher_form": view.github_publisher_form,
            "gitlab_publisher_form": view.gitlab_publisher_form,
            "google_publisher_form": view.google_publisher_form,
            "activestate_publisher_form": view.activestate_publisher_form,
            "prefilled_provider": prefilled_data["provider"].lower(),
        }

        # The form data does not contain the provider, so we'll remove it from
        # the prefilled data before comparing them
        del prefilled_data["provider"]

        form = getattr(view, form_name)
        assert form.data == prefilled_data

    @pytest.mark.parametrize(
        ("missing_fields", "prefilled_data", "extra_fields"),
        [
            # Only some fields present
            (
                ["repository", "environment"],
                {
                    "provider": "github",
                    "owner": "owner",
                    "workflow_filename": "file.yml",
                },
                [],
            ),
            # Extra fields present
            (
                [],
                {
                    "provider": "github",
                    "owner": "owner",
                    "repository": "repo",
                    "workflow_filename": "file.yml",
                    "environment": "my_env",
                    "extra_field_1": "value1",
                    "extra_field_2": "value2",
                },
                ["extra_field_1", "extra_field_2"],
            ),
            # Both missing fields and extra fields present
            (
                ["owner", "repository"],
                {
                    "provider": "github",
                    "workflow_filename": "file.yml",
                    "environment": "my_env",
                    "extra_field_1": "value1",
                    "extra_field_2": "value2",
                },
                ["extra_field_1", "extra_field_2"],
            ),
        ],
    )
    def test_manage_project_oidc_publishers_prefill_partial(
        self, monkeypatch, missing_fields, prefilled_data, extra_fields
    ):
        project = pretend.stub(oidc_publishers=[])
        request = pretend.stub(
            user=pretend.stub(),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                },
            ),
            find_service=lambda *a, **kw: None,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            POST=MultiDict(),
            params=MultiDict(prefilled_data),
        )

        view = views.ManageOIDCPublisherViews(project, request)
        assert view.manage_project_oidc_publishers_prefill() == {
            "disabled": {
                "GitHub": False,
                "GitLab": False,
                "Google": False,
                "ActiveState": False,
            },
            "project": project,
            "github_publisher_form": view.github_publisher_form,
            "gitlab_publisher_form": view.gitlab_publisher_form,
            "google_publisher_form": view.google_publisher_form,
            "activestate_publisher_form": view.activestate_publisher_form,
            "prefilled_provider": prefilled_data["provider"].lower(),
        }

        # The form data does not contain the provider, so we'll remove it from
        # the prefilled data before comparing them
        del prefilled_data["provider"]

        missing_data = {k: None for k in missing_fields}
        # The expected form data is the prefilled data plus the missing fields
        # (set to None) minus the extra fields
        expected_data = prefilled_data | missing_data
        expected_data = {
            k: v for k, v in expected_data.items() if k not in extra_fields
        }
        assert view.github_publisher_form.data == expected_data

    def test_manage_project_oidc_publishers_prefill_unknown_provider(self, monkeypatch):
        project = pretend.stub(oidc_publishers=[])
        prefilled_data = {
            "provider": "github2",
            "owner": "owner",
            "repository": "repo",
            "workflow_filename": "file.yml",
            "environment": "my_env",
        }
        request = pretend.stub(
            user=pretend.stub(),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                },
            ),
            find_service=lambda *a, **kw: None,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            POST=MultiDict(),
            params=MultiDict(prefilled_data),
        )

        view = views.ManageOIDCPublisherViews(project, request)
        assert view.manage_project_oidc_publishers_prefill() == {
            "disabled": {
                "GitHub": False,
                "GitLab": False,
                "Google": False,
                "ActiveState": False,
            },
            "project": project,
            "github_publisher_form": view.github_publisher_form,
            "gitlab_publisher_form": view.gitlab_publisher_form,
            "google_publisher_form": view.google_publisher_form,
            "activestate_publisher_form": view.activestate_publisher_form,
            "prefilled_provider": None,
        }

        assert all(v is None for _, v in view.github_publisher_form.data.items())

    @pytest.mark.parametrize(
        ("publisher", "new_environment_name"),
        [
            (
                GitHubPublisher(
                    repository_name="some-repository",
                    repository_owner="some-owner",
                    repository_owner_id="666",
                    workflow_filename="some-workflow-filename.yml",
                    environment="",
                ),
                "fakeenv",
            ),
            (
                GitLabPublisher(
                    namespace="some-namespace",
                    project="some-project",
                    workflow_filepath="some-workflow-filename.yml",
                    environment="",
                ),
                "fakeenv",
            ),
        ],
    )
    def test_manage_project_oidc_publishers_constrain_environment(
        self,
        monkeypatch,
        metrics,
        db_request,
        publisher,
        new_environment_name,
    ):
        owner = UserFactory.create()
        db_request.user = owner

        project = ProjectFactory.create(oidc_publishers=[publisher])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)
        RoleFactory.create(user=owner, project=project, role_name="Owner")

        db_request.db.add(publisher)
        db_request.db.flush()  # To get the id

        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "constrained_publisher_id": str(publisher.id),
                "constrained_environment_name": new_environment_name,
            }
        )
        db_request.find_service = lambda *a, **kw: metrics
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request._ = lambda s: s
        view = views.ManageOIDCPublisherViews(project, db_request)

        assert isinstance(view.constrain_environment(), HTTPSeeOther)
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.constrain_publisher_environment.attempt",
            ),
        ]

        # The old publisher is actually removed entirely from the DB
        # and replaced by the new constrained publisher.
        publishers = db_request.db.query(OIDCPublisher).all()
        assert len(publishers) == 1
        constrained_publisher = publishers[0]
        assert constrained_publisher.environment == new_environment_name
        assert project.oidc_publishers == [constrained_publisher]

        assert project.record_event.calls == [
            pretend.call(
                tag=EventTag.Project.OIDCPublisherAdded,
                request=db_request,
                additional={
                    "publisher": constrained_publisher.publisher_name,
                    "id": str(constrained_publisher.id),
                    "specifier": str(constrained_publisher),
                    "url": publisher.publisher_url(),
                    "submitted_by": db_request.user.username,
                    "reified_from_pending_publisher": False,
                    "constrained_from_existing_publisher": True,
                },
            ),
            pretend.call(
                tag=EventTag.Project.OIDCPublisherRemoved,
                request=db_request,
                additional={
                    "publisher": publisher.publisher_name,
                    "id": str(publisher.id),
                    "specifier": str(publisher),
                    "url": publisher.publisher_url(),
                    "submitted_by": db_request.user.username,
                },
            ),
        ]
        assert db_request.flags.disallow_oidc.calls == [pretend.call()]
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Trusted publisher for project {project.name!r} has been "
                f"constrained to environment {new_environment_name!r}",
                queue="success",
            )
        ]

    def test_manage_project_oidc_publishers_constrain_environment_shared_publisher(
        self,
        metrics,
        db_request,
    ):
        publisher = GitHubPublisher(
            repository_name="some-repository",
            repository_owner="some-owner",
            repository_owner_id="666",
            workflow_filename="some-workflow-filename.yml",
            environment="",
        )
        owner = UserFactory.create()
        db_request.user = owner

        project = ProjectFactory.create(oidc_publishers=[publisher])
        other_project = ProjectFactory.create(oidc_publishers=[publisher])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)
        RoleFactory.create(user=owner, project=project, role_name="Owner")

        db_request.db.add(publisher)
        db_request.db.flush()  # To get the id

        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "constrained_publisher_id": str(publisher.id),
                "constrained_environment_name": "fakeenv",
            }
        )
        db_request.find_service = lambda *a, **kw: metrics
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request._ = lambda s: s
        view = views.ManageOIDCPublisherViews(project, db_request)

        assert isinstance(view.constrain_environment(), HTTPSeeOther)
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.constrain_publisher_environment.attempt",
            ),
        ]

        # The old publisher is should still be present in the DB, because other_project
        # still uses it.
        assert db_request.db.query(OIDCPublisher).count() == 2
        assert (
            db_request.db.query(GitHubPublisher)
            .filter(GitHubPublisher.environment == "")
            .filter(GitHubPublisher.projects.contains(other_project))
            .count()
        ) == 1

        # The new constrained publisher should exist, and associated to the current
        # project
        constrained_publisher = (
            db_request.db.query(GitHubPublisher)
            .filter(GitHubPublisher.environment == "fakeenv")
            .one()
        )
        assert project.oidc_publishers == [constrained_publisher]

        assert project.record_event.calls == [
            pretend.call(
                tag=EventTag.Project.OIDCPublisherAdded,
                request=db_request,
                additional={
                    "publisher": constrained_publisher.publisher_name,
                    "id": str(constrained_publisher.id),
                    "specifier": str(constrained_publisher),
                    "url": publisher.publisher_url(),
                    "submitted_by": db_request.user.username,
                    "reified_from_pending_publisher": False,
                    "constrained_from_existing_publisher": True,
                },
            ),
            pretend.call(
                tag=EventTag.Project.OIDCPublisherRemoved,
                request=db_request,
                additional={
                    "publisher": publisher.publisher_name,
                    "id": str(publisher.id),
                    "specifier": str(publisher),
                    "url": publisher.publisher_url(),
                    "submitted_by": db_request.user.username,
                },
            ),
        ]
        assert db_request.flags.disallow_oidc.calls == [pretend.call()]
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Trusted publisher for project {project.name!r} has been "
                f"constrained to environment 'fakeenv'",
                queue="success",
            )
        ]

    def test_constrain_oidc_publisher_admin_disabled(self, monkeypatch):
        project = pretend.stub()
        request = pretend.stub(
            method="POST",
            params=MultiDict(),
            user=pretend.stub(),
            find_service=lambda *a, **kw: None,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: True)
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            _=lambda s: s,
            POST=MultiDict(
                {
                    "constrained_publisher_id": uuid.uuid4(),
                    "constrained_environment_name": "fakeenv",
                }
            ),
            registry=pretend.stub(settings={}),
        )

        view = views.ManageOIDCPublisherViews(project, request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.constrain_environment() == default_response
        assert request.session.flash.calls == [
            pretend.call(
                (
                    "Trusted publishing is temporarily disabled. See "
                    "https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
        ]

    def test_constrain_oidc_publisher_invalid_params(self, monkeypatch, metrics):
        project = pretend.stub()
        request = pretend.stub(
            method="POST",
            params=MultiDict(),
            user=pretend.stub(),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            _=lambda s: s,
            POST=MultiDict(
                {
                    "constrained_publisher_id": "not_an_uuid",
                    "constrained_environment_name": "fakeenv",
                }
            ),
            registry=pretend.stub(settings={}),
        )

        view = views.ManageOIDCPublisherViews(project, request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.constrain_environment() == default_response
        assert view.metrics.increment.calls == [
            pretend.call("warehouse.oidc.constrain_publisher_environment.attempt")
        ]
        assert request.session.flash.calls == [
            pretend.call(
                "The trusted publisher could not be constrained",
                queue="error",
            )
        ]

    def test_constrain_non_extant_oidc_publisher(
        self, monkeypatch, metrics, db_request
    ):
        project = pretend.stub()
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "constrained_publisher_id": str(uuid.uuid4()),
                "constrained_environment_name": "fakeenv",
            }
        )
        db_request.find_service = lambda *a, **kw: metrics
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )

        view = views.ManageOIDCPublisherViews(project, db_request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.constrain_environment() == default_response
        assert view.metrics.increment.calls == [
            pretend.call("warehouse.oidc.constrain_publisher_environment.attempt")
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "Invalid publisher for project",
                queue="error",
            )
        ]

    def test_constrain_publisher_from_different_project(
        self, monkeypatch, metrics, db_request
    ):
        owner = UserFactory.create()
        db_request.user = owner

        publisher = GitHubPublisher(
            repository_name="some-repository",
            repository_owner="some-owner",
            repository_owner_id="666",
            workflow_filename="some-workflow-filename.yml",
            environment="",
        )

        request_project = ProjectFactory.create(oidc_publishers=[])
        request_project.record_event = pretend.call_recorder(lambda *a, **kw: None)
        RoleFactory.create(user=owner, project=request_project, role_name="Owner")

        ProjectFactory.create(oidc_publishers=[publisher])

        db_request.db.add(publisher)
        db_request.db.flush()  # To get the id

        db_request.params = MultiDict()
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "constrained_publisher_id": str(publisher.id),
                "constrained_environment_name": "fakeenv",
            }
        )
        db_request.find_service = lambda *a, **kw: metrics
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )

        view = views.ManageOIDCPublisherViews(request_project, db_request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.constrain_environment() == default_response
        assert view.metrics.increment.calls == [
            pretend.call("warehouse.oidc.constrain_publisher_environment.attempt")
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "Invalid publisher for project",
                queue="error",
            )
        ]

    @pytest.mark.parametrize(
        "publisher",
        [
            ActiveStatePublisher(
                organization="some-org",
                activestate_project_name="some-project",
                actor="some-user",
                actor_id="some-user-id",
            ),
            GooglePublisher(
                email="some-email@example.com",
                sub="some-sub",
            ),
        ],
    )
    def test_constrain_unsupported_publisher(
        self, monkeypatch, metrics, db_request, publisher
    ):
        owner = UserFactory.create()
        db_request.user = owner
        db_request.db.add(publisher)
        db_request.db.flush()  # To get the id

        project = ProjectFactory.create(oidc_publishers=[publisher])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)
        RoleFactory.create(user=owner, project=project, role_name="Owner")

        db_request.params = MultiDict()
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "constrained_publisher_id": str(publisher.id),
                "constrained_environment_name": "fakeenv",
            }
        )
        db_request.find_service = lambda *a, **kw: metrics
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )

        view = views.ManageOIDCPublisherViews(project, db_request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.constrain_environment() == default_response
        assert view.metrics.increment.calls == [
            pretend.call("warehouse.oidc.constrain_publisher_environment.attempt")
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "Can only constrain the environment for GitHub and GitLab publishers",
                queue="error",
            )
        ]

    def test_constrain_publisher_with_nonempty_environment(
        self, monkeypatch, metrics, db_request
    ):
        owner = UserFactory.create()
        db_request.user = owner

        publisher = GitHubPublisher(
            repository_name="some-repository",
            repository_owner="some-owner",
            repository_owner_id="666",
            workflow_filename="some-workflow-filename.yml",
            environment="env-already-constrained",
        )

        project = ProjectFactory.create(oidc_publishers=[publisher])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)
        RoleFactory.create(user=owner, project=project, role_name="Owner")

        db_request.db.add(publisher)
        db_request.db.flush()  # To get the id

        db_request.params = MultiDict()
        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "constrained_publisher_id": str(publisher.id),
                "constrained_environment_name": "fakeenv",
            }
        )
        db_request.find_service = lambda *a, **kw: metrics
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )

        view = views.ManageOIDCPublisherViews(project, db_request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.constrain_environment() == default_response
        assert view.metrics.increment.calls == [
            pretend.call("warehouse.oidc.constrain_publisher_environment.attempt")
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "Can only constrain the environment for publishers without an "
                "environment configured",
                queue="error",
            )
        ]

    @pytest.mark.parametrize(
        ("publisher_class", "publisher_kwargs"),
        [
            (
                GitHubPublisher,
                {
                    "repository_name": "some-repository",
                    "repository_owner": "some-owner",
                    "repository_owner_id": "666",
                    "workflow_filename": "some-workflow-filename.yml",
                },
            ),
            (
                GitLabPublisher,
                {
                    "namespace": "some-namespace",
                    "project": "some-project",
                    "workflow_filepath": "some-workflow-filename.yml",
                },
            ),
        ],
    )
    def test_constrain_environment_publisher_already_exists(
        self, monkeypatch, metrics, db_request, publisher_class, publisher_kwargs
    ):
        owner = UserFactory.create()
        db_request.user = owner

        # Create unconstrained and constrained versions of the publisher
        unconstrained = publisher_class(environment="", **publisher_kwargs)
        constrained = publisher_class(environment="fakeenv", **publisher_kwargs)

        project = ProjectFactory.create(oidc_publishers=[unconstrained, constrained])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)
        RoleFactory.create(user=owner, project=project, role_name="Owner")

        db_request.db.add_all([unconstrained, constrained])
        db_request.db.flush()  # To get the ids

        db_request.method = "POST"
        db_request.POST = MultiDict(
            {
                "constrained_publisher_id": str(unconstrained.id),
                "constrained_environment_name": "fakeenv",
            }
        )
        db_request.find_service = lambda *a, **kw: metrics
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request._ = lambda s: s

        view = views.ManageOIDCPublisherViews(project, db_request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.constrain_environment() == default_response
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.constrain_publisher_environment.attempt",
            ),
        ]
        assert project.record_event.calls == []
        assert db_request.session.flash.calls == [
            pretend.call(
                f"{unconstrained} is already registered with {project.name}",
                queue="error",
            )
        ]

    @pytest.mark.parametrize(
        ("view_name", "publisher", "make_form"),
        [
            (
                "add_github_oidc_publisher",
                pretend.stub(
                    id="fakeid",
                    publisher_name="GitHub",
                    repository_name="fakerepo",
                    publisher_url=(
                        lambda x=None: "https://github.com/fakeowner/fakerepo"
                    ),
                    owner="fakeowner",
                    owner_id="1234",
                    workflow_filename="fakeworkflow.yml",
                    environment="some-environment",
                ),
                lambda publisher: pretend.stub(
                    validate=pretend.call_recorder(lambda: True),
                    repository=pretend.stub(data=publisher.repository_name),
                    normalized_owner=publisher.owner,
                    workflow_filename=pretend.stub(data=publisher.workflow_filename),
                    normalized_environment=publisher.environment,
                ),
            ),
            (
                "add_gitlab_oidc_publisher",
                pretend.stub(
                    id="fakeid",
                    publisher_name="GitLab",
                    project="fakerepo",
                    publisher_url=(
                        lambda x=None: "https://gitlab.com/fakeowner/fakerepo"
                    ),
                    namespace="fakeowner",
                    workflow_filepath="subfolder/fakeworkflow.yml",
                    environment="some-environment",
                ),
                lambda publisher: pretend.stub(
                    validate=pretend.call_recorder(lambda: True),
                    project=pretend.stub(data=publisher.project),
                    namespace=pretend.stub(data=publisher.namespace),
                    workflow_filepath=pretend.stub(data=publisher.workflow_filepath),
                    normalized_environment=publisher.environment,
                ),
            ),
            (
                "add_google_oidc_publisher",
                pretend.stub(
                    id="fakeid",
                    publisher_name="Google",
                    publisher_url=lambda x=None: None,
                    email="some-environment@example.com",
                    sub="some-sub",
                ),
                lambda publisher: pretend.stub(
                    validate=pretend.call_recorder(lambda: True),
                    email=pretend.stub(data=publisher.email),
                    sub=pretend.stub(data=publisher.sub),
                ),
            ),
            (
                "add_activestate_oidc_publisher",
                pretend.stub(
                    id="fakeid",
                    publisher_name="ActiveState",
                    publisher_url=(
                        lambda x=None: "https://platform.activestate.com/some-org/some-project"  # noqa
                    ),
                    organization="some-org",
                    activestate_project_name="some-project",
                    actor="some-user",
                    actor_id="some-user-id",
                ),
                lambda publisher: pretend.stub(
                    validate=pretend.call_recorder(lambda: True),
                    organization=pretend.stub(data=publisher.organization),
                    project=pretend.stub(data=publisher.activestate_project_name),
                    actor=pretend.stub(data=publisher.actor),
                    actor_id="some-user-id",
                ),
            ),
        ],
    )
    def test_add_oidc_publisher_preexisting(
        self, metrics, monkeypatch, view_name, publisher, make_form
    ):
        # NOTE: Can't set __str__ using pretend.stub()
        monkeypatch.setattr(publisher.__class__, "__str__", lambda s: "fakespecifier")

        project = pretend.stub(
            name="fakeproject",
            oidc_publishers=[],
            record_event=pretend.call_recorder(lambda *a, **kw: None),
            users=[],
        )

        request = pretend.stub(
            user=pretend.stub(
                username="some-user",
            ),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                }
            ),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            POST=pretend.stub(),
            db=pretend.stub(
                query=lambda *a: pretend.stub(
                    filter=lambda *a: pretend.stub(one_or_none=lambda: publisher)
                ),
                add=pretend.call_recorder(lambda o: None),
            ),
            path="request-path",
        )

        publisher_form_obj = make_form(publisher)
        publisher_form_cls = pretend.call_recorder(lambda *a, **kw: publisher_form_obj)
        monkeypatch.setattr(views, "GitHubPublisherForm", publisher_form_cls)
        monkeypatch.setattr(views, "GitLabPublisherForm", publisher_form_cls)
        monkeypatch.setattr(views, "GooglePublisherForm", publisher_form_cls)
        monkeypatch.setattr(views, "ActiveStatePublisherForm", publisher_form_cls)

        view = views.ManageOIDCPublisherViews(project, request)
        monkeypatch.setattr(
            view, "_hit_ratelimits", pretend.call_recorder(lambda: None)
        )
        monkeypatch.setattr(
            view, "_check_ratelimits", pretend.call_recorder(lambda: None)
        )

        assert isinstance(getattr(view, view_name)(), HTTPSeeOther)
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_publisher.attempt",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
            pretend.call(
                "warehouse.oidc.add_publisher.ok",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
        ]
        assert project.record_event.calls == [
            pretend.call(
                tag=EventTag.Project.OIDCPublisherAdded,
                request=request,
                additional={
                    "publisher": publisher.publisher_name,
                    "id": "fakeid",
                    "specifier": "fakespecifier",
                    "url": publisher.publisher_url(),
                    "submitted_by": "some-user",
                    "reified_from_pending_publisher": False,
                    "constrained_from_existing_publisher": False,
                },
            )
        ]
        assert request.session.flash.calls == [
            pretend.call(
                "Added fakespecifier "
                + (
                    f"in {publisher.publisher_url()}"
                    if publisher.publisher_url()
                    else ""
                )
                + " to fakeproject",
                queue="success",
            )
        ]
        assert request.db.add.calls == []
        assert publisher_form_obj.validate.calls == [pretend.call()]
        assert view._hit_ratelimits.calls == [pretend.call()]
        assert view._check_ratelimits.calls == [pretend.call()]
        assert project.oidc_publishers == [publisher]

    @pytest.mark.parametrize(
        ("view_name", "publisher_form_obj", "expected_publisher"),
        [
            (
                "add_github_oidc_publisher",
                pretend.stub(
                    validate=pretend.call_recorder(lambda: True),
                    repository=pretend.stub(data="fakerepo"),
                    normalized_owner="fakeowner",
                    workflow_filename=pretend.stub(data="fakeworkflow.yml"),
                    normalized_environment="some-environment",
                    owner_id="1234",
                ),
                pretend.stub(publisher_name="GitHub"),
            ),
            (
                "add_gitlab_oidc_publisher",
                pretend.stub(
                    validate=pretend.call_recorder(lambda: True),
                    project=pretend.stub(data="fakerepo"),
                    namespace=pretend.stub(data="fakeowner"),
                    workflow_filepath=pretend.stub(data="subfolder/fakeworkflow.yml"),
                    normalized_environment="some-environment",
                ),
                pretend.stub(publisher_name="GitLab"),
            ),
            (
                "add_google_oidc_publisher",
                pretend.stub(
                    validate=pretend.call_recorder(lambda: True),
                    email=pretend.stub(data="some-environment@example.com"),
                    sub=pretend.stub(data="some-sub"),
                ),
                "Google",
            ),
            (
                "add_activestate_oidc_publisher",
                pretend.stub(
                    validate=pretend.call_recorder(lambda: True),
                    id="fakeid",
                    publisher_name="ActiveState",
                    publisher_url=lambda x=None: None,
                    organization=pretend.stub(data="fake-org"),
                    project=pretend.stub(data="fake-project"),
                    actor=pretend.stub(data="fake-actor"),
                    actor_id="some-user-id",
                ),
                "ActiveState",
            ),
        ],
    )
    def test_add_oidc_publisher_created(
        self, metrics, monkeypatch, view_name, publisher_form_obj, expected_publisher
    ):
        fakeuser = pretend.stub()
        project = pretend.stub(
            name="fakeproject",
            oidc_publishers=[],
            record_event=pretend.call_recorder(lambda *a, **kw: None),
            users=[fakeuser],
        )

        request = pretend.stub(
            user=pretend.stub(
                username="some-user",
            ),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                }
            ),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            POST=pretend.stub(),
            db=pretend.stub(
                query=lambda *a: pretend.stub(
                    filter=lambda *a: pretend.stub(one_or_none=lambda: None)
                ),
                add=pretend.call_recorder(lambda o: setattr(o, "id", "fakeid")),
            ),
            path="request-path",
        )

        publisher_form_cls = pretend.call_recorder(lambda *a, **kw: publisher_form_obj)
        monkeypatch.setattr(views, "GitHubPublisherForm", publisher_form_cls)
        monkeypatch.setattr(views, "GitLabPublisherForm", publisher_form_cls)
        monkeypatch.setattr(views, "GooglePublisherForm", publisher_form_cls)
        monkeypatch.setattr(views, "ActiveStatePublisherForm", publisher_form_cls)
        monkeypatch.setattr(
            views,
            "send_trusted_publisher_added_email",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        view = views.ManageOIDCPublisherViews(project, request)
        monkeypatch.setattr(
            view, "_hit_ratelimits", pretend.call_recorder(lambda: None)
        )
        monkeypatch.setattr(
            view, "_check_ratelimits", pretend.call_recorder(lambda: None)
        )

        assert isinstance(getattr(view, view_name)(), HTTPSeeOther)

        assert len(project.oidc_publishers) == 1
        publisher = project.oidc_publishers[0]

        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_publisher.attempt",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
            pretend.call(
                "warehouse.oidc.add_publisher.ok",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
        ]
        assert project.record_event.calls == [
            pretend.call(
                tag=EventTag.Project.OIDCPublisherAdded,
                request=request,
                additional={
                    "publisher": publisher.publisher_name,
                    "id": "fakeid",
                    "specifier": str(publisher),
                    "url": publisher.publisher_url(),
                    "submitted_by": "some-user",
                    "reified_from_pending_publisher": False,
                    "constrained_from_existing_publisher": False,
                },
            )
        ]
        assert request.session.flash.calls == [
            pretend.call(
                f"Added {str(publisher)} "
                + (
                    f"in {publisher.publisher_url()}"
                    if publisher.publisher_url()
                    else ""
                )
                + " to fakeproject",
                queue="success",
            )
        ]
        assert request.db.add.calls == [pretend.call(project.oidc_publishers[0])]
        assert publisher_form_obj.validate.calls == [pretend.call()]
        assert views.send_trusted_publisher_added_email.calls == [
            pretend.call(
                request,
                fakeuser,
                project_name="fakeproject",
                publisher=publisher,
            )
        ]
        assert view._hit_ratelimits.calls == [pretend.call()]
        assert view._check_ratelimits.calls == [pretend.call()]

    @pytest.mark.parametrize(
        ("view_name", "publisher_name", "publisher", "post_body"),
        [
            (
                "add_github_oidc_publisher",
                "GitHub",
                GitHubPublisher(
                    repository_name="some-repository",
                    repository_owner="some-owner",
                    repository_owner_id="666",
                    workflow_filename="some-workflow-filename.yml",
                    environment="some-environment",
                ),
                MultiDict(
                    {
                        "owner": "some-owner",
                        "repository": "some-repository",
                        "workflow_filename": "some-workflow-filename.yml",
                        "environment": "some-environment",
                    }
                ),
            ),
            (
                "add_gitlab_oidc_publisher",
                "GitLab",
                GitLabPublisher(
                    project="some-repository",
                    namespace="some-owner",
                    workflow_filepath="subfolder/some-workflow-filename.yml",
                    environment="some-environment",
                ),
                MultiDict(
                    {
                        "namespace": "some-owner",
                        "project": "some-repository",
                        "workflow_filepath": "subfolder/some-workflow-filename.yml",
                        "environment": "some-environment",
                    }
                ),
            ),
            (
                "add_google_oidc_publisher",
                "Google",
                GooglePublisher(
                    email="some-email@example.com",
                    sub="some-sub",
                ),
                MultiDict(
                    {
                        "email": "some-email@example.com",
                        "sub": "some-sub",
                    }
                ),
            ),
            (
                "add_activestate_oidc_publisher",
                "ActiveState",
                ActiveStatePublisher(
                    organization="some-org",
                    activestate_project_name="some-project",
                    actor="some-user",
                    actor_id="some-user-id",
                ),
                MultiDict(
                    {
                        "organization": "some-org",
                        "project": "some-project",
                        "actor": "some-user",
                    }
                ),
            ),
        ],
    )
    def test_add_oidc_publisher_already_registered_with_project(
        self, monkeypatch, db_request, view_name, publisher_name, publisher, post_body
    ):
        db_request.user = UserFactory.create()
        EmailFactory(user=db_request.user, verified=True, primary=True)
        db_request.db.add(publisher)
        db_request.db.flush()  # To get it in the DB

        project = pretend.stub(
            name="fakeproject",
            oidc_publishers=[publisher],
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )

        db_request.registry = pretend.stub(
            settings={
                "github.token": "fake-api-token",
            }
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = post_body

        view = views.ManageOIDCPublisherViews(project, db_request)
        monkeypatch.setattr(
            views.GitHubPublisherForm,
            "_lookup_owner",
            lambda *a: {"login": "some-owner", "id": "some-owner-id"},
        )

        monkeypatch.setattr(
            views.ActiveStatePublisherForm,
            "_lookup_organization",
            lambda *a: None,
        )

        monkeypatch.setattr(
            views.ActiveStatePublisherForm,
            "_lookup_actor",
            lambda *a: {"user_id": "some-user-id"},
        )

        monkeypatch.setattr(
            view, "_hit_ratelimits", pretend.call_recorder(lambda: None)
        )
        monkeypatch.setattr(
            view, "_check_ratelimits", pretend.call_recorder(lambda: None)
        )

        assert getattr(view, view_name)() == {
            "disabled": {
                "GitHub": False,
                "GitLab": False,
                "Google": False,
                "ActiveState": False,
            },
            "project": project,
            "github_publisher_form": view.github_publisher_form,
            "gitlab_publisher_form": view.gitlab_publisher_form,
            "google_publisher_form": view.google_publisher_form,
            "activestate_publisher_form": view.activestate_publisher_form,
            "prefilled_provider": view.prefilled_provider,
        }
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_publisher.attempt",
                tags=[f"publisher:{publisher_name}"],
            ),
        ]
        assert project.record_event.calls == []
        assert db_request.session.flash.calls == [
            pretend.call(
                f"{str(publisher)} is already registered with fakeproject",
                queue="error",
            )
        ]

    def test_add_oidc_publisher_already_registered_after_normalization(
        self, monkeypatch, db_request
    ):
        publisher = GitHubPublisher(
            repository_name="some-repository",
            repository_owner="some-owner",
            repository_owner_id="666",
            workflow_filename="some-workflow-filename.yml",
            environment="some-environment",
        )
        post_body = MultiDict(
            {
                "owner": "some-owner",
                "repository": "some-repository",
                "workflow_filename": "some-workflow-filename.yml",
                "environment": "SOME-environment",
            }
        )
        db_request.user = UserFactory.create()
        EmailFactory(user=db_request.user, verified=True, primary=True)
        db_request.db.add(publisher)
        db_request.db.flush()  # To get it in the DB

        project = pretend.stub(
            name="fakeproject",
            oidc_publishers=[publisher],
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )

        db_request.registry = pretend.stub(
            settings={
                "github.token": "fake-api-token",
            }
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = post_body

        view = views.ManageOIDCPublisherViews(project, db_request)
        monkeypatch.setattr(
            views.GitHubPublisherForm,
            "_lookup_owner",
            lambda *a: {"login": "some-owner", "id": "some-owner-id"},
        )

        monkeypatch.setattr(
            view, "_hit_ratelimits", pretend.call_recorder(lambda: None)
        )
        monkeypatch.setattr(
            view, "_check_ratelimits", pretend.call_recorder(lambda: None)
        )

        assert view.add_github_oidc_publisher() == {
            "disabled": {
                "GitHub": False,
                "GitLab": False,
                "Google": False,
                "ActiveState": False,
            },
            "project": project,
            "github_publisher_form": view.github_publisher_form,
            "gitlab_publisher_form": view.gitlab_publisher_form,
            "google_publisher_form": view.google_publisher_form,
            "activestate_publisher_form": view.activestate_publisher_form,
            "prefilled_provider": view.prefilled_provider,
        }
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_publisher.attempt",
                tags=["publisher:GitHub"],
            ),
        ]
        assert project.record_event.calls == []
        assert db_request.session.flash.calls == [
            pretend.call(
                f"{str(publisher)} is already registered with fakeproject",
                queue="error",
            )
        ]

    @pytest.mark.parametrize(
        ("view_name", "publisher_name"),
        [
            ("add_github_oidc_publisher", "GitHub"),
            ("add_gitlab_oidc_publisher", "GitLab"),
            ("add_google_oidc_publisher", "Google"),
            ("add_activestate_oidc_publisher", "ActiveState"),
        ],
    )
    def test_add_oidc_publisher_ratelimited(
        self, metrics, monkeypatch, view_name, publisher_name
    ):
        project = pretend.stub()

        request = pretend.stub(
            user=pretend.stub(),
            registry=pretend.stub(settings={}),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            _=lambda s: s,
            POST=MultiDict(),
        )

        view = views.ManageOIDCPublisherViews(project, request)
        monkeypatch.setattr(
            view,
            "_check_ratelimits",
            pretend.call_recorder(
                pretend.raiser(
                    TooManyOIDCRegistrations(
                        resets_in=pretend.stub(total_seconds=lambda: 60)
                    )
                )
            ),
        )

        assert getattr(view, view_name)().__class__ == HTTPTooManyRequests
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_publisher.attempt",
                tags=[f"publisher:{publisher_name}"],
            ),
            pretend.call(
                "warehouse.oidc.add_publisher.ratelimited",
                tags=[f"publisher:{publisher_name}"],
            ),
        ]

    @pytest.mark.parametrize(
        ("view_name", "publisher_name"),
        [
            ("add_github_oidc_publisher", "GitHub"),
            ("add_gitlab_oidc_publisher", "GitLab"),
            ("add_google_oidc_publisher", "Google"),
            ("add_activestate_oidc_publisher", "ActiveState"),
        ],
    )
    def test_add_oidc_publisher_admin_disabled(
        self, monkeypatch, view_name, publisher_name
    ):
        project = pretend.stub()
        request = pretend.stub(
            user=pretend.stub(),
            find_service=lambda *a, **kw: None,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: True)
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            _=lambda s: s,
            POST=MultiDict(),
            registry=pretend.stub(settings={}),
        )

        view = views.ManageOIDCPublisherViews(project, request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert getattr(view, view_name)() == default_response
        assert request.session.flash.calls == [
            pretend.call(
                (
                    f"{publisher_name}-based trusted publishing is temporarily "
                    "disabled. See https://pypi.org/help#admin-intervention for "
                    "details."
                ),
                queue="error",
            )
        ]

    @pytest.mark.parametrize(
        ("view_name", "publisher_name"),
        [
            ("add_github_oidc_publisher", "GitHub"),
            ("add_gitlab_oidc_publisher", "GitLab"),
            ("add_google_oidc_publisher", "Google"),
            ("add_activestate_oidc_publisher", "ActiveState"),
        ],
    )
    def test_add_oidc_publisher_invalid_form(
        self, metrics, monkeypatch, view_name, publisher_name
    ):
        project = pretend.stub()
        request = pretend.stub(
            user=pretend.stub(),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            _=lambda s: s,
            POST=MultiDict(),
            registry=pretend.stub(settings={}),
        )

        publisher_form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: False),
        )
        publisher_form_cls = pretend.call_recorder(lambda *a, **kw: publisher_form_obj)
        monkeypatch.setattr(views, "GitHubPublisherForm", publisher_form_cls)
        monkeypatch.setattr(views, "GitLabPublisherForm", publisher_form_cls)
        monkeypatch.setattr(views, "GooglePublisherForm", publisher_form_cls)
        monkeypatch.setattr(views, "ActiveStatePublisherForm", publisher_form_cls)

        view = views.ManageOIDCPublisherViews(project, request)
        default_response = {
            "github_publisher_form": publisher_form_obj,
            "gitlab_publisher_form": publisher_form_obj,
            "google_publisher_form": publisher_form_obj,
            "activestate_publisher_form": publisher_form_obj,
        }
        monkeypatch.setattr(
            views.ManageOIDCPublisherViews, "default_response", default_response
        )
        monkeypatch.setattr(
            view, "_check_ratelimits", pretend.call_recorder(lambda: None)
        )
        monkeypatch.setattr(
            view, "_hit_ratelimits", pretend.call_recorder(lambda: None)
        )

        assert getattr(view, view_name)() == default_response
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_publisher.attempt",
                tags=[f"publisher:{publisher_name}"],
            ),
        ]
        assert view._hit_ratelimits.calls == [pretend.call()]
        assert view._check_ratelimits.calls == [pretend.call()]
        assert publisher_form_obj.validate.calls == [pretend.call()]

    @pytest.mark.parametrize(
        "publisher",
        [
            GitHubPublisher(
                repository_name="some-repository",
                repository_owner="some-owner",
                repository_owner_id="666",
                workflow_filename="some-workflow-filename.yml",
                environment="some-environment",
            ),
            GitLabPublisher(
                project="some-repository",
                namespace="some-owner",
                workflow_filepath="subfolder/some-workflow-filename.yml",
                environment="some-environment",
            ),
            GooglePublisher(
                email="some-email@example.com",
                sub="some-sub",
            ),
            ActiveStatePublisher(
                organization="some-org",
                activestate_project_name="some-project",
                actor="some-user",
                actor_id="some-user-id",
            ),
        ],
    )
    def test_delete_oidc_publisher_registered_to_multiple_projects(
        self, monkeypatch, db_request, publisher
    ):
        db_request.user = UserFactory.create()
        EmailFactory(user=db_request.user, verified=True, primary=True)
        db_request.db.add(publisher)
        db_request.db.flush()  # To get it in the DB

        project = ProjectFactory.create(oidc_publishers=[publisher])
        project.record_event = pretend.call_recorder(lambda *a, **kw: None)
        RoleFactory.create(user=db_request.user, project=project, role_name="Owner")
        another_project = ProjectFactory.create(oidc_publishers=[publisher])

        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = MultiDict(
            {
                "publisher_id": str(publisher.id),
            }
        )

        monkeypatch.setattr(
            views,
            "send_trusted_publisher_removed_email",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        view = views.ManageOIDCPublisherViews(project, db_request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert isinstance(view.delete_oidc_publisher(), HTTPSeeOther)
        assert publisher not in project.oidc_publishers

        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.delete_publisher.attempt",
            ),
            pretend.call(
                "warehouse.oidc.delete_publisher.ok",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
        ]

        assert project.record_event.calls == [
            pretend.call(
                tag=EventTag.Project.OIDCPublisherRemoved,
                request=db_request,
                additional={
                    "publisher": publisher.publisher_name,
                    "id": str(publisher.id),
                    "specifier": str(publisher),
                    "url": publisher.publisher_url(),
                    "submitted_by": db_request.user.username,
                },
            )
        ]

        assert db_request.flags.disallow_oidc.calls == [pretend.call()]
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Removed trusted publisher for project {project.name!r}",
                queue="success",
            )
        ]

        # The publisher is not actually removed entirely from the DB, since it's
        # registered to other projects that haven't removed it.
        assert db_request.db.query(OIDCPublisher).one() == publisher
        assert another_project.oidc_publishers == [publisher]

        assert views.send_trusted_publisher_removed_email.calls == [
            pretend.call(
                db_request,
                db_request.user,
                project_name=project.name,
                publisher=publisher,
            )
        ]

    @pytest.mark.parametrize(
        "publisher",
        [
            GitHubPublisher(
                repository_name="some-repository",
                repository_owner="some-owner",
                repository_owner_id="666",
                workflow_filename="some-workflow-filename.yml",
                environment="some-environment",
            ),
            GitLabPublisher(
                project="some-repository",
                namespace="some-owner",
                workflow_filepath="subfolder/some-workflow-filename.yml",
                environment="some-environment",
            ),
            GooglePublisher(
                email="some-email@example.com",
                sub="some-sub",
            ),
            ActiveStatePublisher(
                organization="some-org",
                activestate_project_name="some-project",
                actor="some-user",
                actor_id="some-user-id",
            ),
        ],
    )
    def test_delete_oidc_publisher_entirely(self, monkeypatch, db_request, publisher):
        db_request.user = UserFactory.create()
        EmailFactory(user=db_request.user, verified=True, primary=True)
        db_request.db.add(publisher)
        db_request.db.flush()  # To get it in the DB

        project = ProjectFactory.create(oidc_publishers=[publisher])
        RoleFactory.create(user=db_request.user, project=project, role_name="Owner")

        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = MultiDict(
            {
                "publisher_id": str(publisher.id),
            }
        )

        monkeypatch.setattr(
            views,
            "send_trusted_publisher_removed_email",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        view = views.ManageOIDCPublisherViews(project, db_request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert isinstance(view.delete_oidc_publisher(), HTTPSeeOther)
        assert publisher not in project.oidc_publishers

        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.delete_publisher.attempt",
            ),
            pretend.call(
                "warehouse.oidc.delete_publisher.ok",
                tags=[f"publisher:{publisher.publisher_name}"],
            ),
        ]

        events = project.events.all()
        assert len(events) == 1
        event = events[0]
        assert event.tag == EventTag.Project.OIDCPublisherRemoved
        assert str(event.ip_address) == db_request.remote_addr
        assert event.additional == {
            "publisher": publisher.publisher_name,
            "id": str(publisher.id),
            "specifier": str(publisher),
            "url": publisher.publisher_url(),
            "submitted_by": db_request.user.username,
        }

        assert db_request.flags.disallow_oidc.calls == [pretend.call()]
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Removed trusted publisher for project {project.name!r}",
                queue="success",
            )
        ]

        # The publisher is actually removed entirely from the DB.
        assert db_request.db.query(OIDCPublisher).all() == []

        assert views.send_trusted_publisher_removed_email.calls == [
            pretend.call(
                db_request,
                db_request.user,
                project_name=project.name,
                publisher=publisher,
            )
        ]

    def test_delete_oidc_publisher_invalid_form(self, metrics, monkeypatch):
        publisher = pretend.stub()
        project = pretend.stub(oidc_publishers=[publisher])
        request = pretend.stub(
            user=pretend.stub(),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            POST=MultiDict(),
            registry=pretend.stub(settings={}),
        )

        delete_publisher_form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: False),
        )
        delete_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: delete_publisher_form_obj
        )
        monkeypatch.setattr(views, "DeletePublisherForm", delete_publisher_form_cls)

        view = views.ManageOIDCPublisherViews(project, request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.delete_oidc_publisher() == default_response
        assert len(project.oidc_publishers) == 1

        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.delete_publisher.attempt",
            ),
        ]

        assert delete_publisher_form_cls.calls == [pretend.call(request.POST)]
        assert delete_publisher_form_obj.validate.calls == [pretend.call()]

    @pytest.mark.parametrize(
        "other_publisher", [None, pretend.stub(id="different-fakeid")]
    )
    def test_delete_oidc_publisher_not_found(
        self, metrics, monkeypatch, other_publisher
    ):
        publisher = pretend.stub(
            publisher_name="fakepublisher",
            id="fakeid",
        )
        # NOTE: Can't set __str__ using pretend.stub()
        monkeypatch.setattr(publisher.__class__, "__str__", lambda s: "fakespecifier")

        project = pretend.stub(
            oidc_publishers=[publisher],
            name="fakeproject",
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        request = pretend.stub(
            user=pretend.stub(),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            POST=MultiDict(),
            registry=pretend.stub(settings={}),
            db=pretend.stub(
                get=pretend.call_recorder(lambda *a, **kw: other_publisher),
            ),
            remote_addr="0.0.0.0",
        )

        delete_publisher_form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            publisher_id=pretend.stub(data="different-fakeid"),
        )
        delete_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: delete_publisher_form_obj
        )
        monkeypatch.setattr(views, "DeletePublisherForm", delete_publisher_form_cls)

        view = views.ManageOIDCPublisherViews(project, request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.delete_oidc_publisher() == default_response
        assert publisher in project.oidc_publishers  # not deleted
        assert other_publisher not in project.oidc_publishers

        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.delete_publisher.attempt",
            ),
        ]

        assert project.record_event.calls == []
        assert request.session.flash.calls == [
            pretend.call("Invalid publisher for project", queue="error")
        ]

        assert delete_publisher_form_cls.calls == [pretend.call(request.POST)]
        assert delete_publisher_form_obj.validate.calls == [pretend.call()]

    def test_delete_oidc_publisher_admin_disabled(self, monkeypatch):
        project = pretend.stub()
        request = pretend.stub(
            user=pretend.stub(),
            find_service=lambda *a, **kw: None,
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: True)
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            POST=MultiDict(),
            registry=pretend.stub(settings={}),
        )

        view = views.ManageOIDCPublisherViews(project, request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            views.ManageOIDCPublisherViews, "default_response", default_response
        )

        assert view.delete_oidc_publisher() == default_response
        assert request.session.flash.calls == [
            pretend.call(
                (
                    "Trusted publishing is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
        ]


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
