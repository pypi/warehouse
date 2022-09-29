# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import uuid

import pretend
import pytest

from freezegun import freeze_time
from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPNotFound,
    HTTPSeeOther,
    HTTPTooManyRequests,
)
from pyramid.response import Response
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound
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
from warehouse.forklift.legacy import MAX_FILESIZE, MAX_PROJECT_SIZE
from warehouse.macaroons import caveats
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.manage import views
from warehouse.metrics.interfaces import IMetricsService
from warehouse.oidc.interfaces import TooManyOIDCRegistrations
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import (
    OrganizationInvitation,
    OrganizationInvitationStatus,
    OrganizationRole,
    OrganizationRoleType,
    OrganizationType,
    TeamProjectRole,
    TeamProjectRoleType,
    TeamRoleType,
)
from warehouse.packaging.models import (
    File,
    JournalEntry,
    Project,
    Role,
    RoleInvitation,
    User,
)
from warehouse.rate_limiting import IRateLimiter
from warehouse.utils.paginate import paginate_url_factory
from warehouse.utils.project import remove_documentation

from ...common.db.accounts import EmailFactory
from ...common.db.organizations import (
    OrganizationFactory,
    OrganizationInvitationFactory,
    OrganizationProjectFactory,
    OrganizationRoleFactory,
    OrganizationStripeCustomerFactory,
    OrganizationStripeSubscriptionFactory,
    TeamFactory,
    TeamProjectRoleFactory,
    TeamRoleFactory,
)
from ...common.db.packaging import (
    FileFactory,
    JournalEntryFactory,
    ProjectEventFactory,
    ProjectFactory,
    ReleaseFactory,
    RoleFactory,
    RoleInvitationFactory,
    UserFactory,
)
from ...common.db.subscriptions import (
    StripeCustomerFactory,
    StripeSubscriptionFactory,
    StripeSubscriptionPriceFactory,
)


class TestManageAccount:
    @pytest.mark.parametrize(
        "public_email, expected_public_email",
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

        view = views.ManageAccountViews(request)

        monkeypatch.setattr(views.ManageAccountViews, "active_projects", pretend.stub())

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
            pretend.call(user_id=user_id, user_service=user_service)
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

        view = views.ManageAccountViews(db_request)

        assert view.active_projects == [with_sole_owner]

    def test_manage_account(self, monkeypatch):
        user_service = pretend.stub()
        name = pretend.stub()
        request = pretend.stub(
            find_service=lambda *a, **kw: user_service, user=pretend.stub(name=name)
        )
        monkeypatch.setattr(
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.manage_account() == view.default_response
        assert view.request == request
        assert view.user_service == user_service

    def test_save_account(self, monkeypatch):
        update_user = pretend.call_recorder(lambda *a, **kw: None)
        user_service = pretend.stub(update_user=update_user)
        request = pretend.stub(
            POST={"name": "new name", "public_email": ""},
            user=pretend.stub(
                id=pretend.stub(),
                name=pretend.stub(),
                emails=[
                    pretend.stub(
                        primary=True, verified=True, public=True, email=pretend.stub()
                    )
                ],
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda *a, **kw: user_service,
            path="request-path",
        )
        save_account_obj = pretend.stub(validate=lambda: True, data=request.POST)
        monkeypatch.setattr(views, "SaveAccountForm", lambda *a, **kw: save_account_obj)
        monkeypatch.setattr(
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert isinstance(view.save_account(), HTTPSeeOther)
        assert request.session.flash.calls == [
            pretend.call("Account details updated", queue="success")
        ]
        assert update_user.calls == [pretend.call(request.user.id, **request.POST)]

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
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.save_account() == {
            **view.default_response,
            "save_account_form": save_account_obj,
        }
        assert request.session.flash.calls == []
        assert update_user.calls == []

    def test_add_email(self, monkeypatch, pyramid_request):
        email_address = "test@example.com"
        email = pretend.stub(id=pretend.stub(), email=email_address)
        user_service = pretend.stub(
            add_email=pretend.call_recorder(lambda *a, **kw: email),
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        pyramid_request.POST = {"email": email_address}
        pyramid_request.db = pretend.stub(flush=lambda: None)
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        pyramid_request.find_service = lambda a, **kw: user_service
        pyramid_request.user = pretend.stub(
            emails=[], username="username", name="Name", id=pretend.stub()
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(
            views,
            "AddEmailForm",
            lambda *a, **kw: pretend.stub(
                validate=lambda: True, email=pretend.stub(data=email_address)
            ),
        )

        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_email_verification_email", send_email)

        monkeypatch.setattr(
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(pyramid_request)

        assert isinstance(view.add_email(), HTTPSeeOther)
        assert user_service.add_email.calls == [
            pretend.call(pyramid_request.user.id, email_address)
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                f"Email {email_address} added - check your email for "
                + "a verification link",
                queue="success",
            )
        ]
        assert send_email.calls == [
            pretend.call(pyramid_request, (pyramid_request.user, email))
        ]
        assert user_service.record_event.calls == [
            pretend.call(
                pyramid_request.user.id,
                tag="account:email:add",
                additional={"email": email_address},
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
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.add_email() == {
            **view.default_response,
            "add_email_form": add_email_obj,
        }
        assert request.user.emails == []
        assert email_cls.calls == []
        assert request.session.flash.calls == []

    def test_delete_email(self, monkeypatch):
        email = pretend.stub(id=pretend.stub(), primary=False, email=pretend.stub())
        some_other_email = pretend.stub()
        user_service = pretend.stub(
            record_event=pretend.call_recorder(lambda *a, **kw: None)
        )
        request = pretend.stub(
            POST={"delete_email_id": email.id},
            user=pretend.stub(
                id=pretend.stub(), emails=[email, some_other_email], name=pretend.stub()
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
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert isinstance(view.delete_email(), HTTPSeeOther)
        assert request.session.flash.calls == [
            pretend.call(f"Email address {email.email} removed", queue="success")
        ]
        assert request.user.emails == [some_other_email]
        assert user_service.record_event.calls == [
            pretend.call(
                request.user.id,
                tag="account:email:remove",
                additional={"email": email.email},
            )
        ]

    def test_delete_email_not_found(self, monkeypatch):
        email = pretend.stub()

        def raise_no_result():
            raise NoResultFound

        request = pretend.stub(
            POST={"delete_email_id": "missing_id"},
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
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.delete_email() == view.default_response
        assert request.session.flash.calls == [
            pretend.call("Email address not found", queue="error")
        ]
        assert request.user.emails == [email]

    def test_delete_email_is_primary(self, monkeypatch):
        email = pretend.stub(primary=True)

        request = pretend.stub(
            POST={"delete_email_id": "missing_id"},
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
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.delete_email() == view.default_response
        assert request.session.flash.calls == [
            pretend.call("Cannot remove primary email address", queue="error")
        ]
        assert request.user.emails == [email]

    def test_change_primary_email(self, monkeypatch, db_request):
        user = UserFactory()
        old_primary = EmailFactory(primary=True, user=user, email="old")
        new_primary = EmailFactory(primary=False, verified=True, user=user, email="new")

        db_request.user = user

        user_service = pretend.stub(
            record_event=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.find_service = lambda *a, **kw: user_service
        db_request.POST = {"primary_email_id": new_primary.id}
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(db_request)

        send_email = pretend.call_recorder(lambda *a: None)
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
        assert user_service.record_event.calls == [
            pretend.call(
                user.id,
                tag="account:email:primary:change",
                additional={"old_primary": "old", "new_primary": "new"},
            )
        ]

    def test_change_primary_email_without_current(self, monkeypatch, db_request):
        user = UserFactory()
        new_primary = EmailFactory(primary=False, verified=True, user=user)

        db_request.user = user

        user_service = pretend.stub(
            record_event=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.find_service = lambda *a, **kw: user_service
        db_request.POST = {"primary_email_id": new_primary.id}
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(db_request)

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
        assert user_service.record_event.calls == [
            pretend.call(
                user.id,
                tag="account:email:primary:change",
                additional={"old_primary": None, "new_primary": new_primary.email},
            )
        ]

    def test_change_primary_email_not_found(self, monkeypatch, db_request):
        user = UserFactory()
        old_primary = EmailFactory(primary=True, user=user)
        missing_email_id = 9999

        db_request.user = user
        db_request.find_service = lambda *a, **kw: pretend.stub()
        db_request.POST = {"primary_email_id": missing_email_id}
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(db_request)

        assert view.change_primary_email() == view.default_response
        assert db_request.session.flash.calls == [
            pretend.call("Email address not found", queue="error")
        ]
        assert old_primary.primary

    def test_reverify_email(self, monkeypatch):
        email = pretend.stub(
            verified=False,
            email="email_address",
            user=pretend.stub(
                record_event=pretend.call_recorder(lambda *a, **kw: None)
            ),
        )

        request = pretend.stub(
            POST={"reverify_email_id": pretend.stub()},
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
            user=pretend.stub(id=pretend.stub(), username="username", name="Name"),
            remote_addr="0.0.0.0",
            path="request-path",
        )
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_email_verification_email", send_email)
        monkeypatch.setattr(
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert isinstance(view.reverify_email(), HTTPSeeOther)
        assert request.session.flash.calls == [
            pretend.call("Verification email for email_address resent", queue="success")
        ]
        assert send_email.calls == [pretend.call(request, (request.user, email))]
        assert email.user.record_event.calls == [
            pretend.call(
                tag="account:email:reverify",
                ip_address=request.remote_addr,
                additional={"email": email.email},
            )
        ]

    def test_reverify_email_ratelimit_exceeded(self, monkeypatch):
        email = pretend.stub(
            verified=False,
            email="email_address",
            user=pretend.stub(
                record_event=pretend.call_recorder(lambda *a, **kw: None)
            ),
        )

        request = pretend.stub(
            POST={"reverify_email_id": pretend.stub()},
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
            user=pretend.stub(id=pretend.stub(), username="username", name="Name"),
            remote_addr="0.0.0.0",
            path="request-path",
        )
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_email_verification_email", send_email)
        monkeypatch.setattr(
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(request)

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

    def test_reverify_email_not_found(self, monkeypatch):
        def raise_no_result():
            raise NoResultFound

        request = pretend.stub(
            POST={"reverify_email_id": pretend.stub()},
            db=pretend.stub(
                query=lambda *a: pretend.stub(
                    filter=lambda *a: pretend.stub(one=raise_no_result)
                )
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda *a, **kw: pretend.stub(),
            user=pretend.stub(id=pretend.stub()),
        )
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_email_verification_email", send_email)
        monkeypatch.setattr(
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.reverify_email() == view.default_response
        assert request.session.flash.calls == [
            pretend.call("Email address not found", queue="error")
        ]
        assert send_email.calls == []

    def test_reverify_email_already_verified(self, monkeypatch):
        email = pretend.stub(verified=True, email="email_address")

        request = pretend.stub(
            POST={"reverify_email_id": pretend.stub()},
            db=pretend.stub(
                query=lambda *a: pretend.stub(
                    filter=lambda *a: pretend.stub(one=lambda: email)
                )
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda *a, **kw: pretend.stub(),
            user=pretend.stub(id=pretend.stub()),
            path="request-path",
        )
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_email_verification_email", send_email)
        monkeypatch.setattr(
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(request)

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
            record_event=pretend.call_recorder(lambda *a, **kw: None),
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
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert isinstance(view.change_password(), HTTPSeeOther)
        assert request.session.flash.calls == [
            pretend.call("Password updated", queue="success")
        ]
        assert send_email.calls == [pretend.call(request, request.user)]
        assert user_service.update_user.calls == [
            pretend.call(request.user.id, password=new_password)
        ]
        assert user_service.record_event.calls == [
            pretend.call(request.user.id, tag="account:password:change")
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
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(request)

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
            views.ManageAccountViews, "default_response", pretend.stub()
        )
        monkeypatch.setattr(views.ManageAccountViews, "active_projects", [])
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_account_deletion_email", send_email)
        logout_response = pretend.stub()
        logout = pretend.call_recorder(lambda *a: logout_response)
        monkeypatch.setattr(views, "logout", logout)

        view = views.ManageAccountViews(db_request)

        assert view.delete_account() == logout_response

        journal = (
            db_request.db.query(JournalEntry)
            .options(joinedload("submitted_by"))
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
            views.ManageAccountViews, "default_response", pretend.stub()
        )

        view = views.ManageAccountViews(request)

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
            views.ManageAccountViews, "default_response", pretend.stub()
        )

        view = views.ManageAccountViews(request)

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
            views.ManageAccountViews, "default_response", pretend.stub()
        )
        monkeypatch.setattr(
            views.ManageAccountViews, "active_projects", [pretend.stub()]
        )

        view = views.ManageAccountViews(request)

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

        assert isinstance(result, Response)
        assert result.content_type == "image/svg+xml"

    def test_generate_totp_qr_already_provisioned(self, monkeypatch):
        user_service = pretend.stub(get_totp_secret=lambda id: b"secret")
        request = pretend.stub(
            session=pretend.stub(),
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
        )

        view = views.ProvisionTOTPViews(request)
        result = view.generate_totp_qr()

        assert isinstance(result, Response)
        assert result.status_code == 403

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

    def test_totp_provision(self, monkeypatch):
        user_service = pretend.stub(get_totp_secret=lambda id: None)
        request = pretend.stub(
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
                get_totp_secret=lambda: b"secret",
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
        assert result == {
            "provision_totp_secret": base64.b32encode(b"secret").decode(),
            "provision_totp_form": provision_totp_obj,
            "provision_totp_uri": "not_a_real_uri",
        }

    def test_totp_provision_already_provisioned(self, monkeypatch):
        user_service = pretend.stub(get_totp_secret=lambda id: b"foobar")
        request = pretend.stub(
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
                get_totp_secret=lambda: pretend.stub(),
            ),
            find_service=lambda *a, **kw: user_service,
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                email=pretend.stub(),
                name=pretend.stub(),
                has_primary_verified_email=True,
                has_burned_recovery_codes=True,
            ),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        view = views.ProvisionTOTPViews(request)
        result = view.totp_provision()

        assert isinstance(result, HTTPSeeOther)
        assert result.status_code == 303
        assert result.headers["Location"] == "/foo/bar/"
        assert request.session.flash.calls == [
            pretend.call(
                "Account cannot be linked to more than one authentication "
                "application at a time",
                queue="error",
            )
        ]

    @pytest.mark.parametrize(
        "user, expected_flash_calls",
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

    def test_validate_totp_provision(self, monkeypatch):
        user_service = pretend.stub(
            get_totp_secret=lambda id: None,
            update_user=pretend.call_recorder(lambda *a, **kw: None),
            record_event=pretend.call_recorder(lambda *a, **kw: None),
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
        assert user_service.record_event.calls == [
            pretend.call(
                request.user.id,
                tag="account:two_factor:method_added",
                additional={"method": "totp"},
            )
        ]
        assert send_email.calls == [
            pretend.call(request, request.user, method="totp"),
        ]

    def test_validate_totp_provision_already_provisioned(self, monkeypatch):
        user_service = pretend.stub(
            get_totp_secret=lambda id: b"secret",
            update_user=pretend.call_recorder(lambda *a, **kw: None),
        )
        request = pretend.stub(
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
                get_totp_secret=lambda: pretend.stub(),
            ),
            find_service=lambda *a, **kw: user_service,
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                email=pretend.stub(),
                name=pretend.stub(),
                has_primary_verified_email=True,
            ),
            route_path=pretend.call_recorder(lambda *a, **kw: "/foo/bar"),
        )

        view = views.ProvisionTOTPViews(request)
        result = view.validate_totp_provision()

        assert user_service.update_user.calls == []
        assert request.route_path.calls == [pretend.call("manage.account")]
        assert request.session.flash.calls == [
            pretend.call(
                "Account cannot be linked to more than one authentication "
                "application at a time",
                queue="error",
            )
        ]

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar"

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
            record_event=pretend.call_recorder(lambda *a, **kw: None),
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
        assert user_service.record_event.calls == [
            pretend.call(
                request.user.id,
                tag="account:two_factor:method_removed",
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
            record_event=pretend.call_recorder(lambda *a, **kw: None),
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
        assert user_service.record_event.calls == [
            pretend.call(
                request.user.id,
                tag="account:two_factor:method_added",
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
        user_service = pretend.stub(
            record_event=pretend.call_recorder(lambda *a, **kw: None)
        )
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
        assert user_service.record_event.calls == [
            pretend.call(
                request.user.id,
                tag="account:two_factor:method_removed",
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
                id=1234, username=pretend.stub(), webauthn=[pretend.stub()]
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


class TestProvisionRecoveryCodes:
    def test_recovery_codes_generate(self, monkeypatch):
        user_service = pretend.stub(
            has_recovery_codes=lambda user_id: False,
            has_two_factor=lambda user_id: True,
            generate_recovery_codes=lambda user_id: ["aaaaaaaaaaaa", "bbbbbbbbbbbb"],
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        request = pretend.stub(
            find_service=lambda interface, **kw: {IUserService: user_service}[
                interface
            ],
            user=pretend.stub(id=1),
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

        assert user_service.record_event.calls == [
            pretend.call(1, tag="account:recovery_codes:generated")
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
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        request = pretend.stub(
            POST={"confirm_password": "correct password"},
            find_service=lambda interface, **kw: {IUserService: user_service}[
                interface
            ],
            user=pretend.stub(id=1, username="username"),
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

        assert user_service.record_event.calls == [
            pretend.call(1, tag="account:recovery_codes:regenerated")
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
        "user, expected",
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
        request = pretend.stub(find_service=lambda *a, **kw: pretend.stub())

        default_response = {"default": "response"}
        monkeypatch.setattr(
            views.ProvisionMacaroonViews, "default_response", default_response
        )
        view = views.ProvisionMacaroonViews(request)
        result = view.manage_macaroons()

        assert result == default_response

    def test_create_macaroon_not_allowed(self):
        request = pretend.stub(
            route_path=pretend.call_recorder(lambda x: "/foo/bar"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            user=pretend.stub(has_primary_verified_email=False),
            find_service=lambda interface, **kw: pretend.stub(),
        )

        view = views.ProvisionMacaroonViews(request)
        result = view.create_macaroon()

        assert request.route_path.calls == [pretend.call("manage.account")]
        assert request.session.flash.calls == [
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

    def test_create_macaroon(self, monkeypatch):
        macaroon = pretend.stub()
        macaroon_service = pretend.stub(
            create_macaroon=pretend.call_recorder(
                lambda *a, **kw: ("not a real raw macaroon", macaroon)
            )
        )
        user_service = pretend.stub(
            record_event=pretend.call_recorder(lambda *a, **kw: None)
        )
        request = pretend.stub(
            POST={},
            domain=pretend.stub(),
            user=pretend.stub(id="a user id", has_primary_verified_email=True),
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
            )
        ]
        assert result == {
            **default_response,
            "serialized_macaroon": "not a real raw macaroon",
            "macaroon": macaroon,
            "create_macaroon_form": create_macaroon_obj,
        }
        assert user_service.record_event.calls == [
            pretend.call(
                request.user.id,
                tag="account:api_token:added",
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
        record_user_event = pretend.call_recorder(lambda *a, **kw: None)
        record_project_event = pretend.call_recorder(lambda *a, **kw: None)
        user_service = pretend.stub(record_event=record_user_event)
        request = pretend.stub(
            POST={},
            domain=pretend.stub(),
            user=pretend.stub(
                id=pretend.stub(),
                has_primary_verified_email=True,
                username=pretend.stub(),
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
            )
        ]
        assert result == {
            **default_response,
            "serialized_macaroon": "not a real raw macaroon",
            "macaroon": macaroon,
            "create_macaroon_form": create_macaroon_obj,
        }
        assert record_user_event.calls == [
            pretend.call(
                request.user.id,
                tag="account:api_token:added",
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
                tag="project:api_token:added",
                ip_address=request.remote_addr,
                additional={
                    "description": create_macaroon_obj.description.data,
                    "user": request.user.username,
                },
            ),
            pretend.call(
                tag="project:api_token:added",
                ip_address=request.remote_addr,
                additional={
                    "description": create_macaroon_obj.description.data,
                    "user": request.user.username,
                },
            ),
        ]

    def test_delete_macaroon_invalid_form(self, monkeypatch):
        macaroon_service = pretend.stub(
            delete_macaroon=pretend.call_recorder(lambda id: pretend.stub())
        )
        request = pretend.stub(
            POST={"confirm_password": "password", "macaroon_id": "macaroon_id"},
            route_path=pretend.call_recorder(lambda x: pretend.stub()),
            find_service=lambda interface, **kw: {
                IMacaroonService: macaroon_service,
                IUserService: pretend.stub(),
            }[interface],
            referer="/fake/safe/route",
            host=None,
            user=pretend.stub(username=pretend.stub()),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )

        delete_macaroon_obj = pretend.stub(validate=lambda: False)
        delete_macaroon_cls = pretend.call_recorder(
            lambda *a, **kw: delete_macaroon_obj
        )
        monkeypatch.setattr(views, "DeleteMacaroonForm", delete_macaroon_cls)

        view = views.ProvisionMacaroonViews(request)
        result = view.delete_macaroon()

        assert request.route_path.calls == []
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/fake/safe/route"
        assert macaroon_service.delete_macaroon.calls == []
        assert request.session.flash.calls == [
            pretend.call("Invalid credentials. Try again", queue="error")
        ]

    def test_delete_macaroon_dangerous_redirect(self, monkeypatch):
        macaroon_service = pretend.stub(
            delete_macaroon=pretend.call_recorder(lambda id: pretend.stub())
        )
        request = pretend.stub(
            POST={"confirm_password": "password", "macaroon_id": "macaroon_id"},
            route_path=pretend.call_recorder(lambda x: "/safe/route"),
            find_service=lambda interface, **kw: {
                IMacaroonService: macaroon_service,
                IUserService: pretend.stub(),
            }[interface],
            referer="http://google.com/",
            host=None,
            user=pretend.stub(username=pretend.stub()),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )

        delete_macaroon_obj = pretend.stub(validate=lambda: False)
        delete_macaroon_cls = pretend.call_recorder(
            lambda *a, **kw: delete_macaroon_obj
        )
        monkeypatch.setattr(views, "DeleteMacaroonForm", delete_macaroon_cls)

        view = views.ProvisionMacaroonViews(request)
        result = view.delete_macaroon()

        assert request.route_path.calls == [pretend.call("manage.account")]
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/safe/route"
        assert macaroon_service.delete_macaroon.calls == []

    def test_delete_macaroon(self, monkeypatch):
        macaroon = pretend.stub(description="fake macaroon", permissions_caveat="user")
        macaroon_service = pretend.stub(
            delete_macaroon=pretend.call_recorder(lambda id: pretend.stub()),
            find_macaroon=pretend.call_recorder(lambda id: macaroon),
        )
        record_event = pretend.call_recorder(
            pretend.call_recorder(lambda *a, **kw: None)
        )
        user_service = pretend.stub(record_event=record_event)
        request = pretend.stub(
            POST={"confirm_password": "password", "macaroon_id": "macaroon_id"},
            route_path=pretend.call_recorder(lambda x: pretend.stub()),
            find_service=lambda interface, **kw: {
                IMacaroonService: macaroon_service,
                IUserService: user_service,
            }[interface],
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            referer="/fake/safe/route",
            host=None,
            user=pretend.stub(id=pretend.stub(), username=pretend.stub()),
            remote_addr="0.0.0.0",
        )

        delete_macaroon_obj = pretend.stub(
            validate=lambda: True, macaroon_id=pretend.stub(data=pretend.stub())
        )
        delete_macaroon_cls = pretend.call_recorder(
            lambda *a, **kw: delete_macaroon_obj
        )
        monkeypatch.setattr(views, "DeleteMacaroonForm", delete_macaroon_cls)

        view = views.ProvisionMacaroonViews(request)
        result = view.delete_macaroon()

        assert request.route_path.calls == []
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/fake/safe/route"
        assert macaroon_service.delete_macaroon.calls == [
            pretend.call(delete_macaroon_obj.macaroon_id.data)
        ]
        assert macaroon_service.find_macaroon.calls == [
            pretend.call(delete_macaroon_obj.macaroon_id.data)
        ]
        assert request.session.flash.calls == [
            pretend.call("Deleted API token 'fake macaroon'.", queue="success")
        ]
        assert record_event.calls == [
            pretend.call(
                request.user.id,
                tag="account:api_token:removed",
                additional={"macaroon_id": delete_macaroon_obj.macaroon_id.data},
            )
        ]

    def test_delete_macaroon_records_events_for_each_project(self, monkeypatch):
        macaroon = pretend.stub(
            description="fake macaroon",
            permissions_caveat={"projects": ["foo", "bar"]},
        )
        macaroon_service = pretend.stub(
            delete_macaroon=pretend.call_recorder(lambda id: pretend.stub()),
            find_macaroon=pretend.call_recorder(lambda id: macaroon),
        )
        record_user_event = pretend.call_recorder(lambda *a, **kw: None)
        record_project_event = pretend.call_recorder(lambda *a, **kw: None)
        user_service = pretend.stub(record_event=record_user_event)
        request = pretend.stub(
            POST={"confirm_password": pretend.stub(), "macaroon_id": pretend.stub()},
            route_path=pretend.call_recorder(lambda x: pretend.stub()),
            find_service=lambda interface, **kw: {
                IMacaroonService: macaroon_service,
                IUserService: user_service,
            }[interface],
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            referer="/fake/safe/route",
            host=None,
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                projects=[
                    pretend.stub(
                        normalized_name="foo", record_event=record_project_event
                    ),
                    pretend.stub(
                        normalized_name="bar", record_event=record_project_event
                    ),
                ],
            ),
            remote_addr="0.0.0.0",
        )

        delete_macaroon_obj = pretend.stub(
            validate=lambda: True, macaroon_id=pretend.stub(data=pretend.stub())
        )
        delete_macaroon_cls = pretend.call_recorder(
            lambda *a, **kw: delete_macaroon_obj
        )
        monkeypatch.setattr(views, "DeleteMacaroonForm", delete_macaroon_cls)

        view = views.ProvisionMacaroonViews(request)
        result = view.delete_macaroon()

        assert request.route_path.calls == []
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/fake/safe/route"
        assert macaroon_service.delete_macaroon.calls == [
            pretend.call(delete_macaroon_obj.macaroon_id.data)
        ]
        assert macaroon_service.find_macaroon.calls == [
            pretend.call(delete_macaroon_obj.macaroon_id.data)
        ]
        assert request.session.flash.calls == [
            pretend.call("Deleted API token 'fake macaroon'.", queue="success")
        ]
        assert record_user_event.calls == [
            pretend.call(
                request.user.id,
                tag="account:api_token:removed",
                additional={"macaroon_id": delete_macaroon_obj.macaroon_id.data},
            )
        ]
        assert record_project_event.calls == [
            pretend.call(
                tag="project:api_token:removed",
                ip_address=request.remote_addr,
                additional={
                    "description": "fake macaroon",
                    "user": request.user.username,
                },
            ),
            pretend.call(
                tag="project:api_token:removed",
                ip_address=request.remote_addr,
                additional={
                    "description": "fake macaroon",
                    "user": request.user.username,
                },
            ),
        ]


class TestManageOrganizations:
    def test_default_response(self, monkeypatch):
        create_organization_obj = pretend.stub()
        create_organization_cls = pretend.call_recorder(
            lambda *a, **kw: create_organization_obj
        )
        monkeypatch.setattr(views, "CreateOrganizationForm", create_organization_cls)

        organization = pretend.stub(name=pretend.stub(), is_approved=None)

        user_organizations = pretend.call_recorder(
            lambda *a, **kw: {
                "organizations_managed": [],
                "organizations_owned": [organization],
                "organizations_billing": [],
            }
        )
        monkeypatch.setattr(views, "user_organizations", user_organizations)

        organization_service = pretend.stub(
            get_organizations_by_user=lambda *a, **kw: [organization],
            get_organization_invites_by_user=lambda *a, **kw: [],
        )
        user_service = pretend.stub()
        request = pretend.stub(
            user=pretend.stub(id=pretend.stub(), username=pretend.stub()),
            find_service=lambda interface, **kw: {
                IOrganizationService: organization_service,
                IUserService: user_service,
            }[interface],
        )

        view = views.ManageOrganizationsViews(request)

        assert view.default_response == {
            "organization_invites": [],
            "organizations": [organization],
            "organizations_managed": [],
            "organizations_owned": [organization.name],
            "organizations_billing": [],
            "create_organization_form": create_organization_obj,
        }

    def test_manage_organizations(self, monkeypatch):
        request = pretend.stub(
            find_service=lambda *a, **kw: pretend.stub(),
            flags=pretend.stub(enabled=pretend.call_recorder(lambda f: False)),
        )

        default_response = {"default": "response"}
        monkeypatch.setattr(
            views.ManageOrganizationsViews, "default_response", default_response
        )
        view = views.ManageOrganizationsViews(request)
        result = view.manage_organizations()

        assert result == default_response

    def test_manage_organizations_disable_organizations(self):
        request = pretend.stub(
            find_service=lambda *a, **kw: pretend.stub(),
            flags=pretend.stub(enabled=pretend.call_recorder(lambda f: True)),
        )

        view = views.ManageOrganizationsViews(request)
        with pytest.raises(HTTPNotFound):
            view.manage_organizations()

    def test_create_organization(self, enable_organizations, monkeypatch):
        admins = []
        user_service = pretend.stub(
            get_admins=pretend.call_recorder(lambda *a, **kw: admins),
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )

        organization = pretend.stub(
            id=pretend.stub(),
            name="psf",
            display_name="Python Software Foundation",
            orgtype="Community",
            link_url="https://www.python.org/psf/",
            description=(
                "To promote, protect, and advance the Python programming "
                "language, and to support and facilitate the growth of a "
                "diverse and international community of Python programmers"
            ),
            is_active=False,
            is_approved=None,
        )
        catalog_entry = pretend.stub()
        role = pretend.stub()
        organization_service = pretend.stub(
            add_organization=pretend.call_recorder(lambda *a, **kw: organization),
            add_catalog_entry=pretend.call_recorder(lambda *a, **kw: catalog_entry),
            add_organization_role=pretend.call_recorder(lambda *a, **kw: role),
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )

        request = pretend.stub(
            POST={
                "name": organization.name,
                "display_name": organization.display_name,
                "orgtype": organization.orgtype,
                "link_url": organization.link_url,
                "description": organization.description,
            },
            domain=pretend.stub(),
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                has_primary_verified_email=True,
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda interface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[interface],
            flags=pretend.stub(enabled=pretend.call_recorder(lambda f: False)),
            remote_addr="0.0.0.0",
            path="request-path",
        )

        create_organization_obj = pretend.stub(
            data=request.POST,
            orgtype=pretend.stub(data=request.POST["orgtype"]),
            validate=lambda: True,
        )
        create_organization_cls = pretend.call_recorder(
            lambda *a, **kw: create_organization_obj
        )
        monkeypatch.setattr(views, "CreateOrganizationForm", create_organization_cls)

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views, "send_admin_new_organization_requested_email", send_email
        )
        monkeypatch.setattr(views, "send_new_organization_requested_email", send_email)

        default_response = {"default": "response"}
        monkeypatch.setattr(
            views.ManageOrganizationsViews, "default_response", default_response
        )

        view = views.ManageOrganizationsViews(request)
        result = view.create_organization()

        assert user_service.get_admins.calls == [pretend.call()]
        assert organization_service.add_organization.calls == [
            pretend.call(
                name=organization.name,
                display_name=organization.display_name,
                orgtype=organization.orgtype,
                link_url=organization.link_url,
                description=organization.description,
            )
        ]
        assert organization_service.add_catalog_entry.calls == [
            pretend.call(organization.id)
        ]
        assert organization_service.add_organization_role.calls == [
            pretend.call(
                organization.id,
                request.user.id,
                OrganizationRoleType.Owner,
            )
        ]
        assert organization_service.record_event.calls == [
            pretend.call(
                organization.id,
                tag="organization:create",
                additional={"created_by_user_id": str(request.user.id)},
            ),
            pretend.call(
                organization.id,
                tag="organization:catalog_entry:add",
                additional={"submitted_by_user_id": str(request.user.id)},
            ),
            pretend.call(
                organization.id,
                tag="organization:organization_role:invite",
                additional={
                    "submitted_by_user_id": str(request.user.id),
                    "role_name": "Owner",
                    "target_user_id": str(request.user.id),
                },
            ),
            pretend.call(
                organization.id,
                tag="organization:organization_role:accepted",
                additional={
                    "submitted_by_user_id": str(request.user.id),
                    "role_name": "Owner",
                    "target_user_id": str(request.user.id),
                },
            ),
        ]
        assert user_service.record_event.calls == [
            pretend.call(
                request.user.id,
                tag="account:organization_role:accepted",
                additional={
                    "submitted_by_user_id": str(request.user.id),
                    "organization_name": organization.name,
                    "role_name": "Owner",
                },
            ),
        ]
        assert send_email.calls == [
            pretend.call(
                request,
                admins,
                organization_name=organization.name,
                initiator_username=request.user.username,
                organization_id=organization.id,
            ),
            pretend.call(
                request,
                request.user,
                organization_name=organization.name,
            ),
        ]
        assert isinstance(result, HTTPSeeOther)

    def test_create_organization_with_subscription(
        self, enable_organizations, monkeypatch
    ):
        admins = []
        user_service = pretend.stub(
            get_admins=pretend.call_recorder(lambda *a, **kw: admins),
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )

        organization = pretend.stub(
            id=pretend.stub(),
            name="psf",
            normalized_name="psf",
            display_name="Python Software Foundation",
            orgtype="Company",
            link_url="https://www.python.org/psf/",
            description=(
                "To promote, protect, and advance the Python programming "
                "language, and to support and facilitate the growth of a "
                "diverse and international community of Python programmers"
            ),
            is_active=False,
            is_approved=None,
        )
        catalog_entry = pretend.stub()
        role = pretend.stub()
        organization_service = pretend.stub(
            add_organization=pretend.call_recorder(lambda *a, **kw: organization),
            add_catalog_entry=pretend.call_recorder(lambda *a, **kw: catalog_entry),
            add_organization_role=pretend.call_recorder(lambda *a, **kw: role),
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )

        request = pretend.stub(
            POST={
                "name": organization.name,
                "display_name": organization.display_name,
                "orgtype": organization.orgtype,
                "link_url": organization.link_url,
                "description": organization.description,
            },
            domain=pretend.stub(),
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                has_primary_verified_email=True,
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda interface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[interface],
            flags=pretend.stub(enabled=pretend.call_recorder(lambda f: False)),
            remote_addr="0.0.0.0",
            route_path=lambda *a, **kw: "manage-subscription-url",
        )

        create_organization_obj = pretend.stub(
            data=request.POST,
            orgtype=pretend.stub(data=request.POST["orgtype"]),
            validate=lambda: True,
        )
        create_organization_cls = pretend.call_recorder(
            lambda *a, **kw: create_organization_obj
        )
        monkeypatch.setattr(views, "CreateOrganizationForm", create_organization_cls)

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views, "send_admin_new_organization_requested_email", send_email
        )
        monkeypatch.setattr(views, "send_new_organization_requested_email", send_email)

        default_response = {"default": "response"}
        monkeypatch.setattr(
            views.ManageOrganizationsViews, "default_response", default_response
        )

        view = views.ManageOrganizationsViews(request)
        result = view.create_organization()

        assert user_service.get_admins.calls == [pretend.call()]
        assert organization_service.add_organization.calls == [
            pretend.call(
                name=organization.name,
                display_name=organization.display_name,
                orgtype=organization.orgtype,
                link_url=organization.link_url,
                description=organization.description,
            )
        ]
        assert organization_service.add_catalog_entry.calls == [
            pretend.call(organization.id)
        ]
        assert organization_service.add_organization_role.calls == [
            pretend.call(
                organization.id,
                request.user.id,
                OrganizationRoleType.Owner,
            )
        ]
        assert organization_service.record_event.calls == [
            pretend.call(
                organization.id,
                tag="organization:create",
                additional={"created_by_user_id": str(request.user.id)},
            ),
            pretend.call(
                organization.id,
                tag="organization:catalog_entry:add",
                additional={"submitted_by_user_id": str(request.user.id)},
            ),
            pretend.call(
                organization.id,
                tag="organization:organization_role:invite",
                additional={
                    "submitted_by_user_id": str(request.user.id),
                    "role_name": "Owner",
                    "target_user_id": str(request.user.id),
                },
            ),
            pretend.call(
                organization.id,
                tag="organization:organization_role:accepted",
                additional={
                    "submitted_by_user_id": str(request.user.id),
                    "role_name": "Owner",
                    "target_user_id": str(request.user.id),
                },
            ),
        ]
        assert user_service.record_event.calls == [
            pretend.call(
                request.user.id,
                tag="account:organization_role:accepted",
                additional={
                    "submitted_by_user_id": str(request.user.id),
                    "organization_name": organization.name,
                    "role_name": "Owner",
                },
            ),
        ]
        assert send_email.calls == [
            pretend.call(
                request,
                admins,
                organization_name=organization.name,
                initiator_username=request.user.username,
                organization_id=organization.id,
            ),
            pretend.call(
                request,
                request.user,
                organization_name=organization.name,
            ),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "manage-subscription-url"

    def test_create_organization_validation_fails(self, monkeypatch):
        admins = []
        user_service = pretend.stub(
            get_admins=pretend.call_recorder(lambda *a, **kw: admins),
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )

        organization = pretend.stub()
        catalog_entry = pretend.stub()
        role = pretend.stub()
        organization_service = pretend.stub(
            add_organization=pretend.call_recorder(lambda *a, **kw: organization),
            add_catalog_entry=pretend.call_recorder(lambda *a, **kw: catalog_entry),
            add_organization_role=pretend.call_recorder(lambda *a, **kw: role),
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )

        request = pretend.stub(
            POST={
                "name": None,
                "display_name": None,
                "orgtype": None,
                "link_url": None,
                "description": None,
            },
            domain=pretend.stub(),
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                has_primary_verified_email=True,
            ),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda interface, **kw: {
                IUserService: user_service,
                IOrganizationService: organization_service,
            }[interface],
            flags=pretend.stub(enabled=pretend.call_recorder(lambda f: False)),
            remote_addr="0.0.0.0",
        )

        create_organization_obj = pretend.stub(
            validate=lambda: False, data=request.POST
        )
        create_organization_cls = pretend.call_recorder(
            lambda *a, **kw: create_organization_obj
        )
        monkeypatch.setattr(views, "CreateOrganizationForm", create_organization_cls)

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views, "send_admin_new_organization_requested_email", send_email
        )
        monkeypatch.setattr(views, "send_new_organization_requested_email", send_email)

        view = views.ManageOrganizationsViews(request)
        result = view.create_organization()

        assert user_service.get_admins.calls == []
        assert organization_service.add_organization.calls == []
        assert organization_service.add_catalog_entry.calls == []
        assert organization_service.add_organization_role.calls == []
        assert organization_service.record_event.calls == []
        assert send_email.calls == []
        assert result == {"create_organization_form": create_organization_obj}

    def test_create_organization_disable_organizations(self):
        request = pretend.stub(
            find_service=lambda *a, **kw: pretend.stub(),
            flags=pretend.stub(enabled=pretend.call_recorder(lambda f: True)),
        )

        view = views.ManageOrganizationsViews(request)
        with pytest.raises(HTTPNotFound):
            view.create_organization()


class TestManageOrganizationSettings:
    def test_manage_organization(
        self, db_request, organization_service, enable_organizations, monkeypatch
    ):
        organization = OrganizationFactory.create()
        OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )

        save_organization_obj = pretend.stub()
        save_organization_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_obj
        )
        monkeypatch.setattr(views, "SaveOrganizationForm", save_organization_cls)

        save_organization_name_obj = pretend.stub()
        save_organization_name_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_name_obj
        )
        monkeypatch.setattr(
            views, "SaveOrganizationNameForm", save_organization_name_cls
        )

        view = views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.manage_organization()

        assert view.request == db_request
        assert view.organization_service == organization_service
        assert result == {
            "organization": organization,
            "save_organization_form": save_organization_obj,
            "save_organization_name_form": save_organization_name_obj,
            "active_projects": view.active_projects,
        }
        assert save_organization_cls.calls == [
            pretend.call(
                name=organization.name,
                display_name=organization.display_name,
                link_url=organization.link_url,
                description=organization.description,
                orgtype=organization.orgtype,
                organization_service=organization_service,
            ),
        ]

    def test_save_organization(
        self, db_request, organization_service, enable_organizations, monkeypatch
    ):
        organization = OrganizationFactory.create()
        db_request.POST = {
            "display_name": organization.display_name,
            "link_url": organization.link_url,
            "description": organization.description,
            "orgtype": organization.orgtype,
        }

        monkeypatch.setattr(
            organization_service,
            "update_organization",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        save_organization_obj = pretend.stub(
            validate=lambda: True, data=db_request.POST
        )
        save_organization_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_obj
        )
        monkeypatch.setattr(views, "SaveOrganizationForm", save_organization_cls)

        view = views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.save_organization()

        assert isinstance(result, HTTPSeeOther)
        assert organization_service.update_organization.calls == [
            pretend.call(organization.id, **db_request.POST)
        ]

    def test_save_organization_validation_fails(
        self, db_request, organization_service, enable_organizations, monkeypatch
    ):
        organization = OrganizationFactory.create()
        db_request.POST = {
            "display_name": organization.display_name,
            "link_url": organization.link_url,
            "description": organization.description,
            "orgtype": organization.orgtype,
        }

        monkeypatch.setattr(
            organization_service,
            "update_organization",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        save_organization_obj = pretend.stub(
            validate=lambda: False, data=db_request.POST
        )
        save_organization_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_obj
        )
        monkeypatch.setattr(views, "SaveOrganizationForm", save_organization_cls)

        save_organization_name_obj = pretend.stub()
        save_organization_name_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_name_obj
        )
        monkeypatch.setattr(
            views, "SaveOrganizationNameForm", save_organization_name_cls
        )

        view = views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.save_organization()

        assert result == {
            **view.default_response,
            "save_organization_form": save_organization_obj,
        }
        assert organization_service.update_organization.calls == []

    def test_save_organization_name(
        self,
        db_request,
        pyramid_user,
        organization_service,
        user_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create(name="foobar")
        db_request.POST = {
            "confirm_current_organization_name": organization.name,
            "name": "FooBar",
        }
        db_request.route_path = pretend.call_recorder(
            lambda *a, organization_name, **kw: (
                f"/manage/organization/{organization_name}/settings/"
            )
        )

        def rename_organization(organization_id, organization_name):
            organization.name = organization_name

        monkeypatch.setattr(
            organization_service,
            "rename_organization",
            pretend.call_recorder(rename_organization),
        )

        admins = []
        monkeypatch.setattr(
            user_service,
            "get_admins",
            pretend.call_recorder(lambda *a, **kw: admins),
        )

        save_organization_obj = pretend.stub()
        save_organization_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_obj
        )
        monkeypatch.setattr(views, "SaveOrganizationForm", save_organization_cls)

        save_organization_name_obj = pretend.stub(
            validate=lambda: True, name=pretend.stub(data=db_request.POST["name"])
        )
        save_organization_name_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_name_obj
        )
        monkeypatch.setattr(
            views, "SaveOrganizationNameForm", save_organization_name_cls
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_admin_organization_renamed_email", send_email)
        monkeypatch.setattr(views, "send_organization_renamed_email", send_email)
        monkeypatch.setattr(
            views, "organization_owners", lambda *a, **kw: [pyramid_user]
        )

        view = views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.save_organization_name()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == (
            f"/manage/organization/{organization.normalized_name}/settings/#modal-close"
        )
        assert organization_service.rename_organization.calls == [
            pretend.call(organization.id, "FooBar")
        ]
        assert send_email.calls == [
            pretend.call(
                db_request,
                admins,
                organization_name="FooBar",
                previous_organization_name="foobar",
            ),
            pretend.call(
                db_request,
                {pyramid_user},
                organization_name="FooBar",
                previous_organization_name="foobar",
            ),
        ]

    def test_save_organization_name_wrong_confirm(
        self, db_request, organization_service, enable_organizations, monkeypatch
    ):
        organization = OrganizationFactory.create(name="foobar")
        db_request.POST = {
            "confirm_current_organization_name": organization.name.upper(),
            "name": "FooBar",
        }
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        view = views.ManageOrganizationSettingsViews(organization, db_request)
        with pytest.raises(HTTPSeeOther):
            view.save_organization_name()

        assert db_request.session.flash.calls == [
            pretend.call(
                (
                    "Could not rename organization - "
                    "'FOOBAR' is not the same as 'foobar'"
                ),
                queue="error",
            )
        ]

    def test_save_organization_name_validation_fails(
        self, db_request, organization_service, enable_organizations, monkeypatch
    ):
        organization = OrganizationFactory.create(name="foobar")
        db_request.POST = {
            "confirm_current_organization_name": organization.name,
            "name": "FooBar",
        }

        def rename_organization(organization_id, organization_name):
            organization.name = organization_name

        monkeypatch.setattr(
            organization_service,
            "rename_organization",
            pretend.call_recorder(rename_organization),
        )

        save_organization_obj = pretend.stub()
        save_organization_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_obj
        )
        monkeypatch.setattr(views, "SaveOrganizationForm", save_organization_cls)

        save_organization_name_obj = pretend.stub(
            validate=lambda: False, errors=pretend.stub(values=lambda: ["Invalid"])
        )
        save_organization_name_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_name_obj
        )
        monkeypatch.setattr(
            views, "SaveOrganizationNameForm", save_organization_name_cls
        )

        view = views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.save_organization_name()

        assert result == {
            **view.default_response,
            "save_organization_name_form": save_organization_name_obj,
        }
        assert organization_service.rename_organization.calls == []

    def test_delete_organization(
        self,
        db_request,
        pyramid_user,
        organization_service,
        user_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        db_request.POST = {"confirm_organization_name": organization.name}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations/"
        )

        monkeypatch.setattr(
            organization_service,
            "delete_organization",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        admins = []
        monkeypatch.setattr(
            user_service,
            "get_admins",
            pretend.call_recorder(lambda *a, **kw: admins),
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_admin_organization_deleted_email", send_email)
        monkeypatch.setattr(views, "send_organization_deleted_email", send_email)
        monkeypatch.setattr(
            views, "organization_owners", lambda *a, **kw: [pyramid_user]
        )

        view = views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.delete_organization()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organizations/"
        assert organization_service.delete_organization.calls == [
            pretend.call(organization.id)
        ]
        assert send_email.calls == [
            pretend.call(
                db_request,
                admins,
                organization_name=organization.name,
            ),
            pretend.call(
                db_request,
                {pyramid_user},
                organization_name=organization.name,
            ),
        ]
        assert db_request.route_path.calls == [pretend.call("manage.organizations")]

    def test_delete_organization_with_active_projects(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )

        db_request.POST = {"confirm_organization_name": organization.name}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations/"
        )

        save_organization_obj = pretend.stub()
        save_organization_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_obj
        )
        monkeypatch.setattr(views, "SaveOrganizationForm", save_organization_cls)

        save_organization_name_obj = pretend.stub()
        save_organization_name_cls = pretend.call_recorder(
            lambda *a, **kw: save_organization_name_obj
        )
        monkeypatch.setattr(
            views, "SaveOrganizationNameForm", save_organization_name_cls
        )

        monkeypatch.setattr(
            organization_service,
            "delete_organization",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        view = views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.delete_organization()

        assert result == view.default_response
        assert organization_service.delete_organization.calls == []
        assert db_request.route_path.calls == []

    def test_delete_organization_with_subscriptions(
        self,
        db_request,
        pyramid_user,
        organization_service,
        user_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = StripeSubscriptionFactory.create(customer=stripe_customer)
        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )

        db_request.POST = {"confirm_organization_name": organization.name}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations/"
        )

        monkeypatch.setattr(
            organization_service,
            "delete_organization",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        admins = []
        monkeypatch.setattr(
            user_service,
            "get_admins",
            pretend.call_recorder(lambda *a, **kw: admins),
        )

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_admin_organization_deleted_email", send_email)
        monkeypatch.setattr(views, "send_organization_deleted_email", send_email)
        monkeypatch.setattr(
            views, "organization_owners", lambda *a, **kw: [pyramid_user]
        )

        view = views.ManageOrganizationSettingsViews(organization, db_request)
        result = view.delete_organization()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organizations/"
        assert organization_service.delete_organization.calls == [
            pretend.call(organization.id)
        ]
        assert send_email.calls == [
            pretend.call(
                db_request,
                admins,
                organization_name=organization.name,
            ),
            pretend.call(
                db_request,
                {pyramid_user},
                organization_name=organization.name,
            ),
        ]
        assert db_request.route_path.calls == [pretend.call("manage.organizations")]


class TestManageOrganizationBillingViews:
    @pytest.fixture
    def organization(self):
        organization = OrganizationFactory.create()
        OrganizationStripeCustomerFactory.create(organization=organization)
        return organization

    @pytest.fixture
    def organization_no_customer(self):
        return OrganizationFactory.create()

    @pytest.fixture
    def subscription(self, organization):
        return StripeSubscriptionFactory.create(
            stripe_customer_id=organization.customer.customer_id
        )

    @pytest.fixture
    def organization_subscription(self, organization, subscription):
        return OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )

    @pytest.fixture
    def subscription_price(self):
        return StripeSubscriptionPriceFactory.create()

    def test_customer_id(
        self,
        db_request,
        subscription_service,
        organization,
    ):
        billing_service = pretend.stub(
            create_customer=lambda *a, **kw: {"id": organization.customer.customer_id},
        )

        view = views.ManageOrganizationBillingViews(organization, db_request)
        view.billing_service = billing_service
        customer_id = view.customer_id

        assert customer_id == organization.customer.customer_id

    def test_customer_id_local_mock(
        self,
        db_request,
        billing_service,
        subscription_service,
        organization_no_customer,
    ):
        db_request.registry.settings["site.name"] = "PyPI"

        view = views.ManageOrganizationBillingViews(
            organization_no_customer, db_request
        )
        customer_id = view.customer_id

        assert customer_id.startswith("mockcus_")

    def test_disable_organizations(
        self,
        db_request,
        billing_service,
        subscription_service,
        organization,
    ):
        view = views.ManageOrganizationBillingViews(organization, db_request)

        with pytest.raises(HTTPNotFound):
            view.create_or_manage_subscription()

    def test_activate_subscription(
        self,
        db_request,
        organization,
        enable_organizations,
    ):
        view = views.ManageOrganizationBillingViews(organization, db_request)
        result = view.activate_subscription()

        assert result == {"organization": organization}

    def test_create_subscription(
        self,
        db_request,
        subscription_service,
        organization,
        subscription_price,
        enable_organizations,
        monkeypatch,
    ):
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "mock-session-url"
        )

        # Stub for billing service is not instance of MockStripeBillingService.
        create_checkout_session = pretend.call_recorder(
            lambda *a, **kw: {"url": "session-url"}
        )

        billing_service = pretend.stub(
            create_checkout_session=create_checkout_session,
            create_customer=lambda *a, **kw: {"id": organization.customer.customer_id},
            sync_price=lambda *a, **kw: None,
            sync_product=lambda *a, **kw: None,
        )

        view = views.ManageOrganizationBillingViews(organization, db_request)
        view.billing_service = billing_service
        result = view.create_or_manage_subscription()

        assert create_checkout_session.calls == [
            pretend.call(
                customer_id=organization.customer.customer_id,
                price_ids=[subscription_price.price_id],
                success_url=view.return_url,
                cancel_url=view.return_url,
            ),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "session-url"

    def test_create_subscription_local_mock(
        self,
        db_request,
        billing_service,
        subscription_service,
        organization,
        subscription_price,
        enable_organizations,
        monkeypatch,
    ):
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "mock-session-url"
        )

        # Fixture for billing service is instance of MockStripeBillingService.
        create_checkout_session = pretend.call_recorder(
            lambda *a, **kw: {"url": "session-url"}
        )
        monkeypatch.setattr(
            billing_service, "create_checkout_session", create_checkout_session
        )

        view = views.ManageOrganizationBillingViews(organization, db_request)
        result = view.create_or_manage_subscription()

        assert create_checkout_session.calls == [
            pretend.call(
                customer_id=view.customer_id,
                price_ids=[subscription_price.price_id],
                success_url=view.return_url,
                cancel_url=view.return_url,
            ),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "mock-session-url"

    def test_manage_subscription(
        self,
        db_request,
        billing_service,
        subscription_service,
        organization,
        organization_subscription,
        enable_organizations,
        monkeypatch,
    ):
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "mock-session-url"
        )

        # Stub for billing service is not instance of MockStripeBillingService.
        create_portal_session = pretend.call_recorder(
            lambda *a, **kw: {"url": "session-url"}
        )
        billing_service = pretend.stub(
            create_portal_session=create_portal_session,
            sync_price=lambda *a, **kw: None,
            sync_product=lambda *a, **kw: None,
        )

        view = views.ManageOrganizationBillingViews(organization, db_request)
        view.billing_service = billing_service
        result = view.create_or_manage_subscription()

        assert create_portal_session.calls == [
            pretend.call(
                customer_id=organization.customer.customer_id,
                return_url=view.return_url,
            ),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "session-url"

    def test_manage_subscription_local_mock(
        self,
        db_request,
        billing_service,
        subscription_service,
        organization,
        organization_subscription,
        enable_organizations,
        monkeypatch,
    ):
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "mock-session-url"
        )

        # Fixture for billing service is instance of MockStripeBillingService.
        create_portal_session = pretend.call_recorder(
            lambda *a, **kw: {"url": "session-url"}
        )
        monkeypatch.setattr(
            billing_service, "create_portal_session", create_portal_session
        )

        view = views.ManageOrganizationBillingViews(organization, db_request)
        result = view.create_or_manage_subscription()

        assert create_portal_session.calls == [
            pretend.call(
                customer_id=organization.customer.customer_id,
                return_url=view.return_url,
            ),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "mock-session-url"


class TestManageOrganizationTeams:
    def test_manage_teams(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        organization.teams = [TeamFactory.create()]

        db_request.POST = MultiDict()

        view = views.ManageOrganizationTeamsViews(organization, db_request)
        result = view.manage_teams()
        form = result["create_team_form"]

        assert view.request == db_request
        assert view.organization_service == organization_service
        assert result == {
            "organization": organization,
            "create_team_form": form,
        }

    def test_manage_teams_disable_organizations(self, db_request):
        organization = OrganizationFactory.create()

        view = views.ManageOrganizationTeamsViews(organization, db_request)
        with pytest.raises(HTTPNotFound):
            view.manage_teams()

    def test_create_team(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        organization.teams = [TeamFactory.create()]

        db_request.POST = MultiDict({"name": "Team Name"})

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )

        def add_team(name, *args, **kwargs):
            team = TeamFactory.create(name=name)
            organization.teams.append(team)
            return team

        monkeypatch.setattr(organization_service, "add_team", add_team)

        send_team_created_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views,
            "send_team_created_email",
            send_team_created_email,
        )

        view = views.ManageOrganizationTeamsViews(organization, db_request)
        result = view.create_team()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == db_request.path
        assert len(organization.teams) == 2
        assert organization.teams[-1].name == "Team Name"
        assert send_team_created_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=organization.name,
                team_name="Team Name",
            )
        ]

    def test_create_team_invalid(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        organization.teams = [TeamFactory.create(name="Used Name")]

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )

        db_request.POST = MultiDict({"name": "Used Name"})

        view = views.ManageOrganizationTeamsViews(organization, db_request)
        result = view.create_team()
        form = result["create_team_form"]

        assert view.request == db_request
        assert view.organization_service == organization_service
        assert result == {
            "organization": organization,
            "create_team_form": form,
        }
        assert form.name.errors == [
            "This team name has already been used. Choose a different team name."
        ]
        assert len(organization.teams) == 1

    def test_create_team_disable_organizations(self, db_request):
        organization = OrganizationFactory.create()

        view = views.ManageOrganizationTeamsViews(organization, db_request)
        with pytest.raises(HTTPNotFound):
            view.create_team()


class TestManageOrganizationProjects:
    def test_manage_organization_projects(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )

        add_organization_project_obj = pretend.stub()
        add_organization_project_cls = pretend.call_recorder(
            lambda *a, **kw: add_organization_project_obj
        )
        monkeypatch.setattr(
            views, "AddOrganizationProjectForm", add_organization_project_cls
        )

        view = views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.manage_organization_projects()

        assert view.request == db_request
        assert view.organization_service == organization_service
        assert result == {
            "organization": organization,
            "active_projects": view.active_projects,
            "projects_owned": set(),
            "projects_sole_owned": set(),
            "projects_requiring_2fa": set(),
            "add_organization_project_form": add_organization_project_obj,
        }
        assert len(add_organization_project_cls.calls) == 1

    def test_add_organization_project_existing_project(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )

        project = ProjectFactory.create()

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )
        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        add_organization_project_obj = pretend.stub(
            add_existing_project=pretend.stub(data=True),
            existing_project_name=pretend.stub(data=project.name),
            validate=lambda *a, **kw: True,
        )
        add_organization_project_cls = pretend.call_recorder(
            lambda *a, **kw: add_organization_project_obj
        )
        monkeypatch.setattr(
            views, "AddOrganizationProjectForm", add_organization_project_cls
        )

        def add_organization_project(*args, **kwargs):
            OrganizationProjectFactory.create(
                organization=organization, project=project
            )

        monkeypatch.setattr(
            organization_service, "add_organization_project", add_organization_project
        )

        send_organization_project_added_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_project_added_email",
            send_organization_project_added_email,
        )

        view = views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.add_organization_project()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == db_request.path
        assert len(add_organization_project_cls.calls) == 1
        assert len(organization.projects) == 2
        assert send_organization_project_added_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=organization.name,
                project_name=project.name,
            )
        ]

    def test_add_organization_project_existing_project_no_individual_owner(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )

        project = ProjectFactory.create()

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )

        add_organization_project_obj = pretend.stub(
            add_existing_project=pretend.stub(data=True),
            existing_project_name=pretend.stub(data=project.name),
            validate=lambda *a, **kw: True,
        )
        add_organization_project_cls = pretend.call_recorder(
            lambda *a, **kw: add_organization_project_obj
        )
        monkeypatch.setattr(
            views, "AddOrganizationProjectForm", add_organization_project_cls
        )

        def add_organization_project(*args, **kwargs):
            OrganizationProjectFactory.create(
                organization=organization, project=project
            )

        monkeypatch.setattr(
            organization_service, "add_organization_project", add_organization_project
        )

        send_organization_project_added_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_project_added_email",
            send_organization_project_added_email,
        )

        view = views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.add_organization_project()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == db_request.path
        assert len(add_organization_project_cls.calls) == 1
        assert len(organization.projects) == 2
        assert send_organization_project_added_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=organization.name,
                project_name=project.name,
            )
        ]

    def test_add_organization_project_existing_project_invalid(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )

        project = ProjectFactory.create()

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )
        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        add_organization_project_obj = pretend.stub(
            add_existing_project=pretend.stub(data=True),
            existing_project_name=pretend.stub(data=project.name),
            validate=lambda *a, **kw: False,
        )
        add_organization_project_cls = pretend.call_recorder(
            lambda *a, **kw: add_organization_project_obj
        )
        monkeypatch.setattr(
            views, "AddOrganizationProjectForm", add_organization_project_cls
        )

        def add_organization_project(*args, **kwargs):
            OrganizationProjectFactory.create(
                organization=organization, project=project
            )

        monkeypatch.setattr(
            organization_service, "add_organization_project", add_organization_project
        )

        view = views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.add_organization_project()

        assert result == {
            "organization": organization,
            "active_projects": view.active_projects,
            "projects_owned": {project.name, organization.projects[0].name},
            "projects_sole_owned": {project.name, organization.projects[0].name},
            "projects_requiring_2fa": set(),
            "add_organization_project_form": add_organization_project_obj,
        }
        assert len(add_organization_project_cls.calls) == 1
        assert len(organization.projects) == 1

    def test_add_organization_project_new_project(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        db_request.help_url = lambda *a, **kw: ""

        organization = OrganizationFactory.create()
        OrganizationProjectFactory(
            organization=organization, project=ProjectFactory.create()
        )

        project = ProjectFactory.create()

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )
        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        add_organization_project_obj = pretend.stub(
            add_existing_project=pretend.stub(data=False),
            new_project_name=pretend.stub(data=project.name),
            validate=lambda *a, **kw: True,
        )
        add_organization_project_cls = pretend.call_recorder(
            lambda *a, **kw: add_organization_project_obj
        )
        monkeypatch.setattr(
            views, "AddOrganizationProjectForm", add_organization_project_cls
        )

        validate_project_name = pretend.call_recorder(lambda *a, **kw: True)
        monkeypatch.setattr(views, "validate_project_name", validate_project_name)

        add_project = pretend.call_recorder(lambda *a, **kw: project)
        monkeypatch.setattr(views, "add_project", add_project)

        def add_organization_project(*args, **kwargs):
            OrganizationProjectFactory.create(
                organization=organization, project=project
            )

        monkeypatch.setattr(
            organization_service, "add_organization_project", add_organization_project
        )

        send_organization_project_added_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_project_added_email",
            send_organization_project_added_email,
        )

        view = views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.add_organization_project()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == db_request.path
        assert validate_project_name.calls == [pretend.call(project.name, db_request)]
        assert add_project.calls == [pretend.call(project.name, db_request)]
        assert len(organization.projects) == 2
        assert send_organization_project_added_email.calls == [
            pretend.call(
                db_request,
                {db_request.user},
                organization_name=organization.name,
                project_name=project.name,
            )
        ]

    def test_add_organization_project_new_project_exception(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )

        project = ProjectFactory.create()

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )
        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        add_organization_project_obj = pretend.stub(
            add_existing_project=pretend.stub(data=False),
            new_project_name=pretend.stub(data=project.name, errors=[]),
            validate=lambda *a, **kw: True,
        )
        add_organization_project_cls = pretend.call_recorder(
            lambda *a, **kw: add_organization_project_obj
        )
        monkeypatch.setattr(
            views, "AddOrganizationProjectForm", add_organization_project_cls
        )

        def validate_project_name(*a, **kw):
            raise HTTPBadRequest("error-message")

        monkeypatch.setattr(views, "validate_project_name", validate_project_name)

        view = views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.add_organization_project()

        assert result == {
            "organization": organization,
            "active_projects": view.active_projects,
            "projects_owned": {project.name, organization.projects[0].name},
            "projects_sole_owned": {project.name, organization.projects[0].name},
            "projects_requiring_2fa": set(),
            "add_organization_project_form": add_organization_project_obj,
        }
        assert add_organization_project_obj.new_project_name.errors == ["error-message"]
        assert len(organization.projects) == 1

    def test_add_organization_project_new_project_name_conflict(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        db_request.help_url = lambda *a, **kw: "help-url"

        organization = OrganizationFactory.create()
        OrganizationProjectFactory.create(
            organization=organization, project=ProjectFactory.create()
        )

        project = ProjectFactory.create()

        OrganizationRoleFactory.create(
            organization=organization, user=db_request.user, role_name="Owner"
        )
        RoleFactory.create(project=project, user=db_request.user, role_name="Owner")

        add_organization_project_obj = pretend.stub(
            add_existing_project=pretend.stub(data=False),
            new_project_name=pretend.stub(data=project.name, errors=[]),
            validate=lambda *a, **kw: True,
        )
        add_organization_project_cls = pretend.call_recorder(
            lambda *a, **kw: add_organization_project_obj
        )
        monkeypatch.setattr(
            views, "AddOrganizationProjectForm", add_organization_project_cls
        )

        view = views.ManageOrganizationProjectsViews(organization, db_request)
        result = view.add_organization_project()

        assert result == {
            "organization": organization,
            "active_projects": view.active_projects,
            "projects_owned": {project.name, organization.projects[0].name},
            "projects_sole_owned": {project.name, organization.projects[0].name},
            "projects_requiring_2fa": set(),
            "add_organization_project_form": add_organization_project_obj,
        }
        assert add_organization_project_obj.new_project_name.errors == [
            (
                "The name {name!r} conflicts with an existing project. "
                "See {projecthelp} for more information."
            ).format(
                name=project.name,
                projecthelp="help-url",
            )
        ]
        assert len(organization.projects) == 1


class TestManageOrganizationRoles:
    def test_get_manage_organization_roles(self, db_request, enable_organizations):
        organization = OrganizationFactory.create(name="foobar")
        form_obj = pretend.stub()

        def form_class(*a, **kw):
            return form_obj

        result = views.manage_organization_roles(
            organization, db_request, _form_class=form_class
        )
        assert result == {
            "organization": organization,
            "roles": set(),
            "invitations": set(),
            "form": form_obj,
        }

    @freeze_time(datetime.datetime.utcnow())
    @pytest.mark.parametrize("orgtype", list(OrganizationType))
    def test_post_new_organization_role(
        self,
        db_request,
        orgtype,
        organization_service,
        user_service,
        token_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create(name="foobar", orgtype=orgtype)
        new_user = UserFactory.create(username="new_user")
        EmailFactory.create(user=new_user, verified=True, primary=True)
        owner_1 = UserFactory.create(username="owner_1")
        owner_2 = UserFactory.create(username="owner_2")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner_1,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner_2,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict(
            {"username": new_user.username, "role_name": "Owner"}
        )
        db_request.user = owner_1
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        send_organization_member_invited_email = pretend.call_recorder(
            lambda r, u, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_member_invited_email",
            send_organization_member_invited_email,
        )
        send_organization_role_verification_email = pretend.call_recorder(
            lambda r, u, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_role_verification_email",
            send_organization_role_verification_email,
        )

        result = views.manage_organization_roles(organization, db_request)

        assert db_request.session.flash.calls == [
            pretend.call(f"Invitation sent to '{new_user.username}'", queue="success")
        ]

        # Only one role invitation is created
        (
            db_request.db.query(OrganizationInvitation)
            .filter(OrganizationInvitation.user == new_user)
            .filter(OrganizationInvitation.organization == organization)
            .one()
        )

        assert isinstance(result, HTTPSeeOther)
        assert send_organization_member_invited_email.calls == [
            pretend.call(
                db_request,
                {owner_1, owner_2},
                user=new_user,
                desired_role=db_request.POST["role_name"],
                initiator_username=db_request.user.username,
                organization_name=organization.name,
                email_token=token_service.dumps(
                    {
                        "action": "email-organization-role-verify",
                        "desired_role": db_request.POST["role_name"],
                        "user_id": new_user.id,
                        "organization_id": organization.id,
                        "submitter_id": db_request.user.id,
                    }
                ),
                token_age=token_service.max_age,
            )
        ]
        assert send_organization_role_verification_email.calls == [
            pretend.call(
                db_request,
                new_user,
                desired_role=db_request.POST["role_name"],
                initiator_username=db_request.user.username,
                organization_name=organization.name,
                email_token=token_service.dumps(
                    {
                        "action": "email-organization-role-verify",
                        "desired_role": db_request.POST["role_name"],
                        "user_id": new_user.id,
                        "organization_id": organization.id,
                        "submitter_id": db_request.user.id,
                    }
                ),
                token_age=token_service.max_age,
            )
        ]

    def test_post_duplicate_organization_role(
        self, db_request, organization_service, user_service, enable_organizations
    ):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            organization=organization,
            user=user,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.POST = pretend.stub()
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data=user.username),
            role_name=pretend.stub(data=role.role_name),
        )
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)

        result = views.manage_organization_roles(
            organization, db_request, _form_class=form_class
        )

        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(
                db_request.POST,
                orgtype=organization.orgtype,
                organization_service=organization_service,
                user_service=user_service,
            ),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "User 'testuser' already has Owner role for organization", queue="error"
            )
        ]

        # No additional roles are created
        assert role == db_request.db.query(OrganizationRole).one()

        assert isinstance(result, HTTPSeeOther)

    @pytest.mark.parametrize("with_email", [True, False])
    def test_post_unverified_email(
        self,
        db_request,
        organization_service,
        user_service,
        enable_organizations,
        with_email,
    ):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        if with_email:
            EmailFactory.create(user=user, verified=False, primary=True)

        db_request.method = "POST"
        db_request.POST = pretend.stub()
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data=user.username),
            role_name=pretend.stub(data=OrganizationRoleType.Owner),
        )
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)

        result = views.manage_organization_roles(
            organization, db_request, _form_class=form_class
        )

        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(
                db_request.POST,
                orgtype=organization.orgtype,
                organization_service=organization_service,
                user_service=user_service,
            ),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "User 'testuser' does not have a verified primary email address "
                "and cannot be added as a Owner for organization",
                queue="error",
            )
        ]

        # No additional roles are created
        assert db_request.db.query(OrganizationRole).all() == []

        assert isinstance(result, HTTPSeeOther)

    def test_cannot_reinvite_organization_role(
        self, db_request, organization_service, user_service, enable_organizations
    ):
        organization = OrganizationFactory.create(name="foobar")
        new_user = UserFactory.create(username="new_user")
        EmailFactory.create(user=new_user, verified=True, primary=True)
        owner_1 = UserFactory.create(username="owner_1")
        owner_2 = UserFactory.create(username="owner_2")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner_1,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner_2,
            role_name=OrganizationRoleType.Owner,
        )
        token_service = db_request.find_service(ITokenService, name="email")
        OrganizationInvitationFactory.create(
            organization=organization,
            user=new_user,
            invite_status=OrganizationInvitationStatus.Pending,
            token=token_service.dumps({"action": "email-organization-role-verify"}),
        )

        db_request.method = "POST"
        db_request.POST = pretend.stub()
        db_request.remote_addr = "10.10.10.10"
        db_request.user = owner_1
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data=new_user.username),
            role_name=pretend.stub(data=OrganizationRoleType.Owner),
        )
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)

        result = views.manage_organization_roles(
            organization, db_request, _form_class=form_class
        )

        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(
                db_request.POST,
                orgtype=organization.orgtype,
                organization_service=organization_service,
                user_service=user_service,
            ),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "User 'new_user' already has an active invite. Please try again later.",
                queue="error",
            )
        ]
        assert isinstance(result, HTTPSeeOther)

    @freeze_time(datetime.datetime.utcnow())
    def test_reinvite_organization_role_after_expiration(
        self,
        db_request,
        organization_service,
        user_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create(name="foobar")
        new_user = UserFactory.create(username="new_user")
        EmailFactory.create(user=new_user, verified=True, primary=True)
        owner_1 = UserFactory.create(username="owner_1")
        owner_2 = UserFactory.create(username="owner_2")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner_1,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            user=owner_2,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )
        token_service = db_request.find_service(ITokenService, name="email")
        OrganizationInvitationFactory.create(
            user=new_user,
            organization=organization,
            invite_status=OrganizationInvitationStatus.Expired,
            token=token_service.dumps({}),
        )

        db_request.method = "POST"
        db_request.POST = pretend.stub()
        db_request.remote_addr = "10.10.10.10"
        db_request.user = owner_1
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data=new_user.username),
            role_name=pretend.stub(data=OrganizationRoleType.Owner),
        )
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)

        send_organization_member_invited_email = pretend.call_recorder(
            lambda r, u, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_member_invited_email",
            send_organization_member_invited_email,
        )
        send_organization_role_verification_email = pretend.call_recorder(
            lambda r, u, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_role_verification_email",
            send_organization_role_verification_email,
        )

        result = views.manage_organization_roles(
            organization, db_request, _form_class=form_class
        )

        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(
                db_request.POST,
                orgtype=organization.orgtype,
                organization_service=organization_service,
                user_service=user_service,
            ),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(f"Invitation sent to '{new_user.username}'", queue="success")
        ]

        # Only one role invitation is created
        (
            db_request.db.query(OrganizationInvitation)
            .filter(OrganizationInvitation.user == new_user)
            .filter(OrganizationInvitation.organization == organization)
            .one()
        )

        assert isinstance(result, HTTPSeeOther)
        assert send_organization_member_invited_email.calls == [
            pretend.call(
                db_request,
                {owner_1, owner_2},
                user=new_user,
                desired_role=form_obj.role_name.data.value,
                initiator_username=db_request.user.username,
                organization_name=organization.name,
                email_token=token_service.dumps(
                    {
                        "action": "email-organization-role-verify",
                        "desired_role": form_obj.role_name.data.value,
                        "user_id": new_user.id,
                        "organization_id": organization.id,
                        "submitter_id": db_request.user.id,
                    }
                ),
                token_age=token_service.max_age,
            )
        ]
        assert send_organization_role_verification_email.calls == [
            pretend.call(
                db_request,
                new_user,
                desired_role=form_obj.role_name.data.value,
                initiator_username=db_request.user.username,
                organization_name=organization.name,
                email_token=token_service.dumps(
                    {
                        "action": "email-organization-role-verify",
                        "desired_role": form_obj.role_name.data.value,
                        "user_id": new_user.id,
                        "organization_id": organization.id,
                        "submitter_id": db_request.user.id,
                    }
                ),
                token_age=token_service.max_age,
            )
        ]


class TestRevokeOrganizationInvitation:
    def test_revoke_invitation(
        self, db_request, token_service, enable_organizations, monkeypatch
    ):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        OrganizationInvitationFactory.create(
            organization=organization,
            user=user,
        )
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            user=owner_user,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"user_id": user.id, "token": "TOKEN"})
        db_request.remote_addr = "10.10.10.10"
        db_request.user = owner_user
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        token_service.loads = pretend.call_recorder(
            lambda data: {
                "action": "email-organization-role-verify",
                "desired_role": "Manager",
                "user_id": user.id,
                "organization_id": organization.id,
                "submitter_id": owner_user.id,
            }
        )

        organization_member_invite_canceled_email = pretend.call_recorder(
            lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_member_invite_canceled_email",
            organization_member_invite_canceled_email,
        )
        canceled_as_invited_organization_member_email = pretend.call_recorder(
            lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            views,
            "send_canceled_as_invited_organization_member_email",
            canceled_as_invited_organization_member_email,
        )

        result = views.revoke_organization_invitation(organization, db_request)
        db_request.db.flush()

        assert not (
            db_request.db.query(OrganizationInvitation)
            .filter(OrganizationInvitation.user == user)
            .filter(OrganizationInvitation.organization == organization)
            .one_or_none()
        )
        assert organization_member_invite_canceled_email.calls == [
            pretend.call(
                db_request,
                {owner_user},
                user=user,
                organization_name=organization.name,
            )
        ]
        assert canceled_as_invited_organization_member_email.calls == [
            pretend.call(
                db_request,
                user,
                organization_name=organization.name,
            )
        ]
        assert db_request.session.flash.calls == [
            pretend.call(f"Invitation revoked from '{user.username}'.", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organizations"

    def test_invitation_does_not_exist(
        self, db_request, token_service, enable_organizations
    ):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            user=owner_user,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"user_id": user.id, "token": "TOKEN"})
        db_request.remote_addr = "10.10.10.10"
        db_request.user = owner_user
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        token_service.loads = pretend.call_recorder(lambda data: None)

        result = views.revoke_organization_invitation(organization, db_request)
        db_request.db.flush()

        assert db_request.session.flash.calls == [
            pretend.call("Could not find organization invitation.", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organizations"

    def test_token_expired(self, db_request, token_service, enable_organizations):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        OrganizationInvitationFactory.create(
            organization=organization,
            user=user,
        )
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            user=owner_user,
            organization=organization,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"user_id": user.id, "token": "TOKEN"})
        db_request.remote_addr = "10.10.10.10"
        db_request.user = owner_user
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations/roles"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        token_service.loads = pretend.call_recorder(pretend.raiser(TokenExpired))

        result = views.revoke_organization_invitation(organization, db_request)
        db_request.db.flush()

        assert not (
            db_request.db.query(OrganizationInvitation)
            .filter(OrganizationInvitation.user == user)
            .filter(OrganizationInvitation.organization == organization)
            .one_or_none()
        )
        assert db_request.session.flash.calls == [
            pretend.call("Invitation already expired.", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organizations/roles"


class TestChangeOrganizationRole:
    @pytest.mark.parametrize("orgtype", list(OrganizationType))
    def test_change_role(self, db_request, orgtype, enable_organizations, monkeypatch):
        organization = OrganizationFactory.create(name="foobar", orgtype=orgtype)
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            organization=organization,
            user=user,
            role_name=OrganizationRoleType.Owner,
        )
        new_role_name = "Manager"

        user_2 = UserFactory.create()

        db_request.method = "POST"
        db_request.POST = MultiDict({"role_id": role.id, "role_name": new_role_name})
        db_request.user = user_2
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        send_organization_member_role_changed_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_member_role_changed_email",
            send_organization_member_role_changed_email,
        )
        send_role_changed_as_organization_member_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            views,
            "send_role_changed_as_organization_member_email",
            send_role_changed_as_organization_member_email,
        )

        result = views.change_organization_role(organization, db_request)

        assert role.role_name == new_role_name
        assert db_request.route_path.calls == [
            pretend.call(
                "manage.organization.roles", organization_name=organization.name
            )
        ]
        assert send_organization_member_role_changed_email.calls == [
            pretend.call(
                db_request,
                set(),
                user=user,
                submitter=user_2,
                organization_name="foobar",
                role=new_role_name,
            )
        ]
        assert send_role_changed_as_organization_member_email.calls == [
            pretend.call(
                db_request,
                user,
                submitter=user_2,
                organization_name="foobar",
                role=new_role_name,
            )
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Changed role", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_change_organization_role_invalid_role_name(
        self, db_request, enable_organizations
    ):
        organization = OrganizationFactory.create(name="foobar")

        db_request.method = "POST"
        db_request.POST = MultiDict(
            {"role_id": str(uuid.uuid4()), "role_name": "Invalid Role Name"}
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.change_organization_role(organization, db_request)

        assert db_request.route_path.calls == [
            pretend.call(
                "manage.organization.roles", organization_name=organization.name
            )
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_change_missing_organization_role(self, db_request, enable_organizations):
        organization = OrganizationFactory.create(name="foobar")
        missing_role_id = str(uuid.uuid4())

        db_request.method = "POST"
        db_request.POST = MultiDict({"role_id": missing_role_id, "role_name": "Owner"})
        db_request.user = pretend.stub()
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.change_organization_role(organization, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Could not find member", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_change_own_owner_organization_role(self, db_request, enable_organizations):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            user=user, organization=organization, role_name="Owner"
        )

        db_request.method = "POST"
        db_request.user = user
        db_request.POST = MultiDict({"role_id": role.id, "role_name": "Manager"})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.change_organization_role(organization, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Cannot remove yourself as Owner", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"


class TestDeleteOrganizationRoles:
    def test_delete_role(self, db_request, enable_organizations, monkeypatch):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            organization=organization,
            user=user,
            role_name=OrganizationRoleType.Owner,
        )
        user_2 = UserFactory.create()

        db_request.method = "POST"
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.user = user_2
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        send_organization_member_removed_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_member_removed_email",
            send_organization_member_removed_email,
        )
        send_removed_as_organization_member_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            views,
            "send_removed_as_organization_member_email",
            send_removed_as_organization_member_email,
        )

        result = views.delete_organization_role(organization, db_request)

        assert db_request.route_path.calls == [
            pretend.call(
                "manage.organization.roles", organization_name=organization.name
            )
        ]
        assert db_request.db.query(OrganizationRole).all() == []
        assert send_organization_member_removed_email.calls == [
            pretend.call(
                db_request,
                set(),
                user=user,
                submitter=user_2,
                organization_name="foobar",
            )
        ]
        assert send_removed_as_organization_member_email.calls == [
            pretend.call(
                db_request,
                user,
                submitter=user_2,
                organization_name="foobar",
            )
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Removed from organization", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_delete_missing_role(self, db_request, enable_organizations):
        organization = OrganizationFactory.create(name="foobar")
        missing_role_id = str(uuid.uuid4())

        db_request.method = "POST"
        db_request.user = pretend.stub()
        db_request.POST = MultiDict({"role_id": missing_role_id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.delete_organization_role(organization, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Could not find member", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_delete_other_role_as_nonowner(self, db_request, enable_organizations):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            organization=organization,
            user=user,
            role_name=OrganizationRoleType.Owner,
        )
        user_2 = UserFactory.create()

        db_request.method = "POST"
        db_request.user = user_2
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.has_permission = pretend.call_recorder(lambda *a, **kw: False)
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.delete_organization_role(organization, db_request)

        assert db_request.has_permission.calls == [pretend.call("manage:organization")]
        assert db_request.session.flash.calls == [
            pretend.call(
                "Cannot remove other people from the organization", queue="error"
            )
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_delete_own_owner_role(self, db_request, enable_organizations):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            organization=organization,
            user=user,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.user = user
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.delete_organization_role(organization, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Cannot remove yourself as Owner", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_delete_non_owner_role(self, db_request, enable_organizations):
        organization = OrganizationFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = OrganizationRoleFactory.create(
            organization=organization,
            user=user,
            role_name=OrganizationRoleType.Owner,
        )

        some_other_user = UserFactory.create(username="someotheruser")
        some_other_organization = OrganizationFactory.create(
            name="someotherorganization"
        )

        db_request.method = "POST"
        db_request.user = some_other_user
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.delete_organization_role(some_other_organization, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Could not find member", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"


class TestManageTeamSettings:
    def test_manage_team(
        self, db_request, organization_service, user_service, enable_organizations
    ):
        team = TeamFactory.create()

        view = views.ManageTeamSettingsViews(team, db_request)
        result = view.manage_team()
        form = result["save_team_form"]

        assert view.request == db_request
        assert view.organization_service == organization_service
        assert view.user_service == user_service
        assert result == {
            "team": team,
            "save_team_form": form,
        }

    def test_save_team(self, db_request, organization_service, enable_organizations):
        team = TeamFactory.create(name="Team Name")
        db_request.POST = MultiDict({"name": "Team name"})
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foo/bar/")

        view = views.ManageTeamSettingsViews(team, db_request)
        result = view.save_team()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar/"
        assert team.name == "Team name"

    def test_save_team_validation_fails(
        self, db_request, organization_service, enable_organizations
    ):
        organization = OrganizationFactory.create()
        team = TeamFactory.create(
            name="Team Name",
            organization=organization,
        )
        TeamFactory.create(
            name="Existing Team Name",
            organization=organization,
        )

        db_request.POST = MultiDict({"name": "Existing Team Name"})

        view = views.ManageTeamSettingsViews(team, db_request)
        result = view.save_team()
        form = result["save_team_form"]

        assert result == {
            "team": team,
            "save_team_form": form,
        }
        assert team.name == "Team Name"
        assert form.name.errors == [
            "This team name has already been used. Choose a different team name."
        ]

    def test_delete_team(
        self,
        db_request,
        pyramid_user,
        organization_service,
        user_service,
        enable_organizations,
        monkeypatch,
    ):
        team = TeamFactory.create()
        db_request.POST = MultiDict({"confirm_team_name": team.name})
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foo/bar/")

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "send_team_deleted_email", send_email)

        view = views.ManageTeamSettingsViews(team, db_request)
        result = view.delete_team()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar/"
        assert send_email.calls == [
            pretend.call(
                db_request,
                set(),
                organization_name=team.organization.name,
                team_name=team.name,
            ),
        ]

    def test_delete_team_no_confirm(
        self,
        db_request,
        pyramid_user,
        organization_service,
        user_service,
        enable_organizations,
        monkeypatch,
    ):
        team = TeamFactory.create()
        db_request.POST = MultiDict()
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foo/bar/")

        view = views.ManageTeamSettingsViews(team, db_request)
        with pytest.raises(HTTPSeeOther):
            view.delete_team()

        assert db_request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]

    def test_delete_team_wrong_confirm(
        self,
        db_request,
        pyramid_user,
        organization_service,
        user_service,
        enable_organizations,
        monkeypatch,
    ):
        team = TeamFactory.create(name="Team Name")
        db_request.POST = MultiDict({"confirm_team_name": "TEAM NAME"})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foo/bar/")

        view = views.ManageTeamSettingsViews(team, db_request)
        with pytest.raises(HTTPSeeOther):
            view.delete_team()

        assert db_request.session.flash.calls == [
            pretend.call(
                (
                    "Could not delete team - "
                    "'TEAM NAME' is not the same as 'Team Name'"
                ),
                queue="error",
            )
        ]


class TestManageTeamProjects:
    def test_manage_team_projects(
        self,
        db_request,
        pyramid_user,
        organization_service,
        enable_organizations,
        monkeypatch,
    ):
        team = TeamFactory.create()
        project = ProjectFactory.create()

        TeamProjectRoleFactory.create(
            project=project, team=team, role_name=TeamProjectRoleType.Owner
        )

        view = views.ManageTeamProjectsViews(team, db_request)
        result = view.manage_team_projects()

        assert view.team == team
        assert view.request == db_request
        assert result == {
            "team": team,
            "active_projects": view.active_projects,
            "projects_owned": set(),
            "projects_sole_owned": set(),
            "projects_requiring_2fa": set(),
        }


class TestManageTeamRoles:
    def test_manage_team_roles(
        self,
        db_request,
        organization_service,
        user_service,
        enable_organizations,
    ):
        team = TeamFactory.create()

        db_request.POST = MultiDict()

        view = views.ManageTeamRolesViews(team, db_request)
        result = view.manage_team_roles()
        form = result["form"]

        assert result == {
            "team": team,
            "roles": [],
            "form": form,
        }

    def test_create_team_role(
        self,
        db_request,
        organization_service,
        user_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        team = TeamFactory(organization=organization)
        owner = UserFactory.create(username="owner")
        manager = UserFactory.create(username="manager")
        member = UserFactory.create(username="user")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=manager,
            role_name=OrganizationRoleType.Manager,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=member,
            role_name=OrganizationRoleType.Member,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"username": member.username})
        db_request.user = owner
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        send_team_member_added_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views,
            "send_team_member_added_email",
            send_team_member_added_email,
        )
        send_added_as_team_member_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views,
            "send_added_as_team_member_email",
            send_added_as_team_member_email,
        )

        view = views.ManageTeamRolesViews(team, db_request)
        result = view.create_team_role()
        roles = organization_service.get_team_roles(team.id)

        assert len(roles) == 1
        assert roles[0].team_id == team.id
        assert roles[0].user_id == member.id
        assert send_team_member_added_email.calls == [
            pretend.call(
                db_request,
                {owner, manager},
                user=member,
                submitter=db_request.user,
                organization_name=team.organization.name,
                team_name=team.name,
            )
        ]
        assert send_added_as_team_member_email.calls == [
            pretend.call(
                db_request,
                member,
                submitter=db_request.user,
                organization_name=team.organization.name,
                team_name=team.name,
            )
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Added the team {team.name!r} to {team.organization.name!r}",
                queue="success",
            )
        ]
        assert isinstance(result, HTTPSeeOther)

    def test_create_team_role_duplicate_member(
        self,
        db_request,
        organization_service,
        user_service,
        enable_organizations,
    ):
        organization = OrganizationFactory.create()
        team = TeamFactory(organization=organization)
        owner = UserFactory.create(username="owner")
        manager = UserFactory.create(username="manager")
        member = UserFactory.create(username="user")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=manager,
            role_name=OrganizationRoleType.Manager,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=member,
            role_name=OrganizationRoleType.Member,
        )
        role = TeamRoleFactory.create(
            team=team,
            user=member,
            role_name=TeamRoleType.Member,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"username": member.username})
        db_request.user = owner
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        view = views.ManageTeamRolesViews(team, db_request)
        result = view.create_team_role()
        form = result["form"]

        assert organization_service.get_team_roles(team.id) == [role]
        assert db_request.session.flash.calls == [
            pretend.call(
                f"User '{member.username}' is already a team member", queue="error"
            )
        ]
        assert result == {
            "team": team,
            "roles": [role],
            "form": form,
        }

    def test_create_team_role_not_a_member(
        self,
        db_request,
        organization_service,
        user_service,
        enable_organizations,
    ):
        organization = OrganizationFactory.create()
        team = TeamFactory(organization=organization)
        owner = UserFactory.create(username="owner")
        manager = UserFactory.create(username="manager")
        not_a_member = UserFactory.create(username="user")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=manager,
            role_name=OrganizationRoleType.Manager,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"username": not_a_member.username})
        db_request.user = owner
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        view = views.ManageTeamRolesViews(team, db_request)
        result = view.create_team_role()
        form = result["form"]

        assert result == {
            "team": team,
            "roles": [],
            "form": form,
        }

        assert form.username.errors == [
            (
                "No organization owner, manager, or member found "
                "with that username. Please try again."
            )
        ]

    def test_delete_team_role(
        self,
        db_request,
        organization_service,
        user_service,
        enable_organizations,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        team = TeamFactory(organization=organization)
        owner = UserFactory.create(username="owner")
        manager = UserFactory.create(username="manager")
        member = UserFactory.create(username="user")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=manager,
            role_name=OrganizationRoleType.Manager,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=member,
            role_name=OrganizationRoleType.Member,
        )
        role = TeamRoleFactory.create(
            team=team,
            user=member,
            role_name=TeamRoleType.Member,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.user = owner
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foo/bar/")

        send_team_member_removed_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views,
            "send_team_member_removed_email",
            send_team_member_removed_email,
        )
        send_removed_as_team_member_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views,
            "send_removed_as_team_member_email",
            send_removed_as_team_member_email,
        )

        view = views.ManageTeamRolesViews(team, db_request)
        result = view.delete_team_role()

        assert organization_service.get_team_roles(team.id) == []
        assert send_team_member_removed_email.calls == [
            pretend.call(
                db_request,
                {owner, manager},
                user=member,
                submitter=db_request.user,
                organization_name=team.organization.name,
                team_name=team.name,
            )
        ]
        assert send_removed_as_team_member_email.calls == [
            pretend.call(
                db_request,
                member,
                submitter=db_request.user,
                organization_name=team.organization.name,
                team_name=team.name,
            )
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Removed from team", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)

    def test_delete_team_role_not_a_member(
        self,
        db_request,
        organization_service,
        user_service,
        enable_organizations,
    ):
        organization = OrganizationFactory.create()
        team = TeamFactory(organization=organization)
        other_team = TeamFactory(organization=organization)
        owner = UserFactory.create(username="owner")
        manager = UserFactory.create(username="manager")
        not_a_member = UserFactory.create(username="user")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=manager,
            role_name=OrganizationRoleType.Manager,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=not_a_member,
            role_name=OrganizationRoleType.Member,
        )
        other_team_role = TeamRoleFactory.create(
            team=other_team,
            user=not_a_member,
            role_name=TeamRoleType.Member,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"role_id": other_team_role.id})
        db_request.user = owner
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foo/bar/")

        view = views.ManageTeamRolesViews(team, db_request)
        result = view.delete_team_role()

        assert organization_service.get_team_roles(team.id) == []
        assert db_request.session.flash.calls == [
            pretend.call("Could not find member", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)

    def test_delete_team_role_not_a_manager(
        self,
        db_request,
        organization_service,
        user_service,
        enable_organizations,
    ):
        organization = OrganizationFactory.create()
        team = TeamFactory(organization=organization)
        owner = UserFactory.create(username="owner")
        not_a_manager = UserFactory.create(username="manager")
        member = UserFactory.create(username="user")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=not_a_manager,
            role_name=OrganizationRoleType.Member,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=member,
            role_name=OrganizationRoleType.Member,
        )
        role = TeamRoleFactory.create(
            team=team,
            user=member,
            role_name=TeamRoleType.Member,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.user = not_a_manager
        db_request.has_permission = lambda *a, **kw: False
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foo/bar/")

        view = views.ManageTeamRolesViews(team, db_request)
        result = view.delete_team_role()

        assert organization_service.get_team_roles(team.id) == [role]
        assert db_request.session.flash.calls == [
            pretend.call("Cannot remove other people from the team", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)


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
        project_where_owners_require_2fa = ProjectFactory(
            releases=[], created=datetime.datetime(2022, 1, 1), owners_require_2fa=True
        )
        project_where_pypi_mandates_2fa = ProjectFactory(
            releases=[], created=datetime.datetime(2022, 1, 2), pypi_mandates_2fa=True
        )
        another_project_where_owners_require_2fa = ProjectFactory(
            releases=[], created=datetime.datetime(2022, 3, 1), owners_require_2fa=True
        )
        another_project_where_pypi_mandates_2fa = ProjectFactory(
            releases=[], created=datetime.datetime(2022, 3, 2), pypi_mandates_2fa=True
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
        RoleFactory.create(
            user=db_request.user,
            project=project_where_owners_require_2fa,
            role_name="Owner",
        )
        RoleFactory.create(
            user=db_request.user,
            project=project_where_pypi_mandates_2fa,
            role_name="Owner",
        )
        RoleFactory.create(
            user=db_request.user,
            project=another_project_where_owners_require_2fa,
            role_name="Maintainer",
        )
        RoleFactory.create(
            user=db_request.user,
            project=another_project_where_pypi_mandates_2fa,
            role_name="Maintainer",
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
                another_project_where_pypi_mandates_2fa,
                another_project_where_owners_require_2fa,
                project_where_pypi_mandates_2fa,
                project_where_owners_require_2fa,
                newer_project_with_no_releases,
                project_with_newer_release,
                older_project_with_no_releases,
                project_with_older_release,
            ],
            "projects_owned": {
                project_with_newer_release.name,
                newer_project_with_no_releases.name,
                project_where_owners_require_2fa.name,
                project_where_pypi_mandates_2fa.name,
            },
            "projects_sole_owned": {
                newer_project_with_no_releases.name,
                project_where_owners_require_2fa.name,
                project_where_pypi_mandates_2fa.name,
            },
            "projects_requiring_2fa": {
                project_where_owners_require_2fa.name,
                project_where_pypi_mandates_2fa.name,
                another_project_where_owners_require_2fa.name,
                another_project_where_pypi_mandates_2fa.name,
            },
            "project_invites": [],
        }


class TestManageProjectSettings:
    @pytest.mark.parametrize("enabled", [False, True])
    def test_manage_project_settings(self, enabled, monkeypatch):
        request = pretend.stub(
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: enabled))
        )
        project = pretend.stub(organization=None)
        view = views.ManageProjectSettingsViews(project, request)
        form = pretend.stub()
        view.toggle_2fa_requirement_form_class = lambda *a, **kw: form
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
            "toggle_2fa_form": form,
            "transfer_organization_project_form": form,
        }

    def test_manage_project_settings_in_organization_managed(self, monkeypatch):
        request = pretend.stub(
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        )
        organization_managed = pretend.stub(name="managed-org", is_active=True)
        organization_owned = pretend.stub(name="owned-org", is_active=True)
        project = pretend.stub(organization=organization_managed)
        view = views.ManageProjectSettingsViews(project, request)
        form = pretend.stub()
        view.toggle_2fa_requirement_form_class = lambda *a, **kw: form
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
            "toggle_2fa_form": form,
            "transfer_organization_project_form": form,
        }
        assert view.transfer_organization_project_form_class.calls == [
            pretend.call(organization_choices={"owned-org"})
        ]

    def test_manage_project_settings_in_organization_owned(self, monkeypatch):
        request = pretend.stub(
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False))
        )
        organization_managed = pretend.stub(name="managed-org", is_active=True)
        organization_owned = pretend.stub(name="owned-org", is_active=True)
        project = pretend.stub(organization=organization_owned)
        view = views.ManageProjectSettingsViews(project, request)
        form = pretend.stub()
        view.toggle_2fa_requirement_form_class = lambda *a, **kw: form
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
            "toggle_2fa_form": form,
            "transfer_organization_project_form": form,
        }
        assert view.transfer_organization_project_form_class.calls == [
            pretend.call(organization_choices={"managed-org"})
        ]

    @pytest.mark.parametrize("enabled", [False, None])
    def test_toggle_2fa_requirement_feature_disabled(self, enabled):
        request = pretend.stub(
            registry=pretend.stub(
                settings={"warehouse.two_factor_requirement.enabled": enabled}
            ),
        )

        project = pretend.stub()
        view = views.ManageProjectSettingsViews(project, request)
        with pytest.raises(HTTPNotFound):
            view.toggle_2fa_requirement()

    @pytest.mark.parametrize(
        "owners_require_2fa, expected, expected_flash_calls",
        [
            (
                False,
                False,
                [
                    pretend.call(
                        "2FA requirement cannot be disabled for critical projects",
                        queue="error",
                    )
                ],
            ),
            (
                True,
                True,
                [
                    pretend.call(
                        "2FA requirement cannot be disabled for critical projects",
                        queue="error",
                    )
                ],
            ),
        ],
    )
    def test_toggle_2fa_requirement_critical(
        self,
        owners_require_2fa,
        expected,
        expected_flash_calls,
        db_request,
    ):
        db_request.registry = pretend.stub(
            settings={"warehouse.two_factor_requirement.enabled": True}
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda message, queue: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foo/bar/")
        db_request.user = pretend.stub(username="foo")

        project = ProjectFactory.create(
            name="foo",
            owners_require_2fa=owners_require_2fa,
            pypi_mandates_2fa=True,
        )
        view = views.ManageProjectSettingsViews(project, db_request)

        result = view.toggle_2fa_requirement()

        assert project.owners_require_2fa == expected
        assert project.pypi_mandates_2fa
        assert db_request.session.flash.calls == expected_flash_calls
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.status_code == 303
        assert result.headers["Location"] == "/foo/bar/"

    @pytest.mark.parametrize(
        "owners_require_2fa, expected, expected_flash_calls, tag",
        [
            (
                False,
                True,
                [pretend.call("2FA requirement enabled for foo", queue="success")],
                "project:owners_require_2fa:enabled",
            ),
            (
                True,
                False,
                [pretend.call("2FA requirement disabled for foo", queue="success")],
                "project:owners_require_2fa:disabled",
            ),
        ],
    )
    def test_toggle_2fa_requirement_non_critical(
        self,
        owners_require_2fa,
        expected,
        expected_flash_calls,
        tag,
        db_request,
    ):
        db_request.registry = pretend.stub(
            settings={"warehouse.two_factor_requirement.enabled": True}
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda message, queue: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foo/bar/")
        db_request.user = pretend.stub(username="foo")

        project = ProjectFactory.create(
            name="foo",
            owners_require_2fa=owners_require_2fa,
            pypi_mandates_2fa=False,
        )
        view = views.ManageProjectSettingsViews(project, db_request)

        result = view.toggle_2fa_requirement()

        assert project.owners_require_2fa == expected
        assert not project.pypi_mandates_2fa
        assert db_request.session.flash.calls == expected_flash_calls
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.status_code == 303
        assert result.headers["Location"] == "/foo/bar/"

        events = project.events.all()
        assert len(events) == 1
        event = events[0]
        assert event.tag == tag
        assert event.additional == {"modified_by": db_request.user.username}

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
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        with pytest.raises(HTTPSeeOther) as exc:
            views.remove_organization_project(project, request)
            assert exc.value.status_code == 303
            assert exc.value.headers["Location"] == "/foo/bar/"

        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISABLE_ORGANIZATIONS)
        ]
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
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        with pytest.raises(HTTPSeeOther) as exc:
            views.remove_organization_project(project, request)
            assert exc.value.status_code == 303
            assert exc.value.headers["Location"] == "/foo/bar/"

        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISABLE_ORGANIZATIONS)
        ]
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
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: True)),
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )

        result = views.remove_organization_project(project, request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISABLE_ORGANIZATIONS)
        ]
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
            views,
            "send_organization_project_removed_email",
            send_organization_project_removed_email,
        )

        result = views.remove_organization_project(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                ("Could not remove project from organization - no organization found"),
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
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        result = views.remove_organization_project(project, request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar/"
        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISABLE_ORGANIZATIONS)
        ]
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

        result = views.remove_organization_project(project, db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert db_request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISABLE_ORGANIZATIONS)
        ]
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
            views,
            "send_organization_project_removed_email",
            send_organization_project_removed_email,
        )

        result = views.remove_organization_project(project, db_request)

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
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        with pytest.raises(HTTPSeeOther) as exc:
            views.transfer_organization_project(project, request)
            assert exc.value.status_code == 303
            assert exc.value.headers["Location"] == "/foo/bar/"

        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISABLE_ORGANIZATIONS)
        ]
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
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        with pytest.raises(HTTPSeeOther) as exc:
            views.transfer_organization_project(project, request)
            assert exc.value.status_code == 303
            assert exc.value.headers["Location"] == "/foo/bar/"

        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISABLE_ORGANIZATIONS)
        ]
        assert request.session.flash.calls == [
            pretend.call(
                "Could not transfer project - 'FOO' is not the same as 'foo'",
                queue="error",
            )
        ]

    def test_transfer_organization_project_disable_organizations(self):
        project = pretend.stub(name="foo", normalized_name="foo")
        request = pretend.stub(
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: True)),
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )

        result = views.transfer_organization_project(project, request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISABLE_ORGANIZATIONS)
        ]

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
                "organization": organization.normalized_name,
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
            views,
            "send_organization_project_removed_email",
            send_organization_project_removed_email,
        )

        send_organization_project_added_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_project_added_email",
            send_organization_project_added_email,
        )

        result = views.transfer_organization_project(project, db_request)

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
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        result = views.transfer_organization_project(project, request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar/"
        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISABLE_ORGANIZATIONS)
        ]
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
                "organization": organization.normalized_name,
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
            views,
            "send_organization_project_removed_email",
            send_organization_project_removed_email,
        )

        send_organization_project_added_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_project_added_email",
            send_organization_project_added_email,
        )

        result = views.transfer_organization_project(project, db_request)

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

        result = views.transfer_organization_project(project, db_request)

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
                "organization": organization.normalized_name,
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
        monkeypatch.setattr(views, "user_organizations", user_organizations)

        transfer_organization_project_form_class = pretend.call_recorder(
            views.TransferOrganizationProjectForm
        )
        monkeypatch.setattr(
            views,
            "TransferOrganizationProjectForm",
            transfer_organization_project_form_class,
        )

        send_organization_project_removed_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_project_removed_email",
            send_organization_project_removed_email,
        )

        send_organization_project_added_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_project_added_email",
            send_organization_project_added_email,
        )

        result = views.transfer_organization_project(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Transferred the project 'foo' to 'baz'", queue="success")
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]
        assert transfer_organization_project_form_class.calls == [
            pretend.call(db_request.POST, organization_choices={"bar-owned", "baz"})
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
                "organization": organization.normalized_name,
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
        monkeypatch.setattr(views, "user_organizations", user_organizations)

        transfer_organization_project_form_class = pretend.call_recorder(
            views.TransferOrganizationProjectForm
        )
        monkeypatch.setattr(
            views,
            "TransferOrganizationProjectForm",
            transfer_organization_project_form_class,
        )

        send_organization_project_removed_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_project_removed_email",
            send_organization_project_removed_email,
        )

        send_organization_project_added_email = pretend.call_recorder(
            lambda req, user, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_project_added_email",
            send_organization_project_added_email,
        )

        result = views.transfer_organization_project(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Transferred the project 'foo' to 'baz'", queue="success")
        ]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.settings", project_name="foo")
        ]
        assert transfer_organization_project_form_class.calls == [
            pretend.call(db_request.POST, organization_choices={"bar-managed", "baz"})
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

    def test_delete_project_disallow_deletion(self):
        project = pretend.stub(name="foo", normalized_name="foo")
        request = pretend.stub(
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: True)),
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )

        result = views.delete_project(project, request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISALLOW_DELETION)
        ]

        assert request.session.flash.calls == [
            pretend.call(
                (
                    "Project deletion temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
        ]

        assert request.route_path.calls == [
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

        assert task.calls == [pretend.call(remove_documentation)]

        assert remove_documentation_recorder.delay.calls == [pretend.call(project.name)]

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

    def test_delete_project_release_disallow_deletion(self, monkeypatch):
        release = pretend.stub(
            version="1.2.3",
            canonical_version="1.2.3",
            project=pretend.stub(
                name="foobar", record_event=pretend.call_recorder(lambda *a, **kw: None)
            ),
        )
        request = pretend.stub(
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: True)),
            method="POST",
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )
        view = views.ManageProjectRelease(release, request)

        result = view.delete_project_release()
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISALLOW_DELETION)
        ]

        assert request.session.flash.calls == [
            pretend.call(
                (
                    "Project deletion temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
        ]

        assert request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_yank_project_release(self, monkeypatch):
        user = pretend.stub(username=pretend.stub())
        release = pretend.stub(
            version="1.2.3",
            canonical_version="1.2.3",
            project=pretend.stub(
                name="foobar",
                record_event=pretend.call_recorder(lambda *a, **kw: None),
                users=[user],
            ),
            created=datetime.datetime(2017, 2, 5, 17, 18, 18, 462_634),
            yanked=False,
            yanked_reason="",
        )
        request = pretend.stub(
            POST={
                "confirm_yank_version": release.version,
                "yanked_reason": "Yanky Doodle went to town",
            },
            method="POST",
            db=pretend.stub(add=pretend.call_recorder(lambda a: None)),
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            user=user,
            remote_addr=pretend.stub(),
        )
        journal_obj = pretend.stub()
        journal_cls = pretend.call_recorder(lambda **kw: journal_obj)

        get_user_role_in_project = pretend.call_recorder(
            lambda project, user, req: "Owner"
        )
        monkeypatch.setattr(views, "get_user_role_in_project", get_user_role_in_project)

        monkeypatch.setattr(views, "JournalEntry", journal_cls)
        send_yanked_project_release_email = pretend.call_recorder(
            lambda req, contrib, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_yanked_project_release_email",
            send_yanked_project_release_email,
        )

        view = views.ManageProjectRelease(release, request)

        result = view.yank_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert release.yanked
        assert release.yanked_reason == "Yanky Doodle went to town"

        assert get_user_role_in_project.calls == [
            pretend.call(release.project, request.user, request),
            pretend.call(release.project, request.user, request),
        ]

        assert send_yanked_project_release_email.calls == [
            pretend.call(
                request,
                request.user,
                release=release,
                submitter_name=request.user.username,
                submitter_role="Owner",
                recipient_role="Owner",
            )
        ]

        assert request.db.add.calls == [pretend.call(journal_obj)]
        assert journal_cls.calls == [
            pretend.call(
                name=release.project.name,
                action="yank release",
                version=release.version,
                submitted_by=request.user,
                submitted_from=request.remote_addr,
            )
        ]
        assert request.session.flash.calls == [
            pretend.call(f"Yanked release {release.version!r}", queue="success")
        ]
        assert request.route_path.calls == [
            pretend.call("manage.project.releases", project_name=release.project.name)
        ]
        assert release.project.record_event.calls == [
            pretend.call(
                tag="project:release:yank",
                ip_address=request.remote_addr,
                additional={
                    "submitted_by": request.user.username,
                    "canonical_version": release.canonical_version,
                    "yanked_reason": "Yanky Doodle went to town",
                },
            )
        ]

    def test_yank_project_release_no_confirm(self):
        release = pretend.stub(
            version="1.2.3",
            project=pretend.stub(name="foobar"),
            yanked=False,
            yanked_reason="",
        )
        request = pretend.stub(
            POST={"confirm_yank_version": ""},
            method="POST",
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )
        view = views.ManageProjectRelease(release, request)

        result = view.yank_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert not release.yanked
        assert not release.yanked_reason

        assert request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]
        assert request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_yank_project_release_bad_confirm(self):
        release = pretend.stub(
            version="1.2.3",
            project=pretend.stub(name="foobar"),
            yanked=False,
            yanked_reason="",
        )
        request = pretend.stub(
            POST={"confirm_yank_version": "invalid"},
            method="POST",
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )
        view = views.ManageProjectRelease(release, request)

        result = view.yank_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert not release.yanked
        assert not release.yanked_reason

        assert request.session.flash.calls == [
            pretend.call(
                "Could not yank release - "
                + f"'invalid' is not the same as {release.version!r}",
                queue="error",
            )
        ]
        assert request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_unyank_project_release(self, monkeypatch):
        user = pretend.stub(username=pretend.stub())
        release = pretend.stub(
            version="1.2.3",
            canonical_version="1.2.3",
            project=pretend.stub(
                name="foobar",
                record_event=pretend.call_recorder(lambda *a, **kw: None),
                users=[user],
            ),
            created=datetime.datetime(2017, 2, 5, 17, 18, 18, 462_634),
            yanked=True,
        )
        request = pretend.stub(
            POST={"confirm_unyank_version": release.version},
            method="POST",
            db=pretend.stub(add=pretend.call_recorder(lambda a: None)),
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            user=user,
            remote_addr=pretend.stub(),
        )
        journal_obj = pretend.stub()
        journal_cls = pretend.call_recorder(lambda **kw: journal_obj)

        get_user_role_in_project = pretend.call_recorder(
            lambda project_name, username, req: "Owner"
        )
        monkeypatch.setattr(views, "get_user_role_in_project", get_user_role_in_project)

        monkeypatch.setattr(views, "JournalEntry", journal_cls)
        send_unyanked_project_release_email = pretend.call_recorder(
            lambda req, contrib, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_unyanked_project_release_email",
            send_unyanked_project_release_email,
        )

        view = views.ManageProjectRelease(release, request)

        result = view.unyank_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert not release.yanked
        assert not release.yanked_reason

        assert get_user_role_in_project.calls == [
            pretend.call(release.project, request.user, request),
            pretend.call(release.project, request.user, request),
        ]

        assert send_unyanked_project_release_email.calls == [
            pretend.call(
                request,
                request.user,
                release=release,
                submitter_name=request.user.username,
                submitter_role="Owner",
                recipient_role="Owner",
            )
        ]

        assert request.db.add.calls == [pretend.call(journal_obj)]
        assert journal_cls.calls == [
            pretend.call(
                name=release.project.name,
                action="unyank release",
                version=release.version,
                submitted_by=request.user,
                submitted_from=request.remote_addr,
            )
        ]
        assert request.session.flash.calls == [
            pretend.call(f"Un-yanked release {release.version!r}", queue="success")
        ]
        assert request.route_path.calls == [
            pretend.call("manage.project.releases", project_name=release.project.name)
        ]
        assert release.project.record_event.calls == [
            pretend.call(
                tag="project:release:unyank",
                ip_address=request.remote_addr,
                additional={
                    "submitted_by": request.user.username,
                    "canonical_version": release.canonical_version,
                },
            )
        ]

    def test_unyank_project_release_no_confirm(self):
        release = pretend.stub(
            version="1.2.3",
            project=pretend.stub(name="foobar"),
            yanked=True,
            yanked_reason="",
        )
        request = pretend.stub(
            POST={
                "confirm_unyank_version": "",
                "yanked_reason": "Yanky Doodle went to town",
            },
            method="POST",
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )
        view = views.ManageProjectRelease(release, request)

        result = view.unyank_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert release.yanked
        assert not release.yanked_reason

        assert request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]
        assert request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_unyank_project_release_bad_confirm(self):
        release = pretend.stub(
            version="1.2.3",
            project=pretend.stub(name="foobar"),
            yanked=True,
            yanked_reason="Old reason",
        )
        request = pretend.stub(
            POST={"confirm_unyank_version": "invalid", "yanked_reason": "New reason"},
            method="POST",
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )
        view = views.ManageProjectRelease(release, request)

        result = view.unyank_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert release.yanked
        assert release.yanked_reason == "Old reason"

        assert request.session.flash.calls == [
            pretend.call(
                "Could not un-yank release - "
                + f"'invalid' is not the same as {release.version!r}",
                queue="error",
            )
        ]
        assert request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_delete_project_release(self, monkeypatch):
        user = pretend.stub(username=pretend.stub())
        release = pretend.stub(
            version="1.2.3",
            canonical_version="1.2.3",
            project=pretend.stub(
                name="foobar",
                record_event=pretend.call_recorder(lambda *a, **kw: None),
                users=[user],
            ),
            created=datetime.datetime(2017, 2, 5, 17, 18, 18, 462_634),
        )
        request = pretend.stub(
            POST={"confirm_delete_version": release.version},
            method="POST",
            db=pretend.stub(
                delete=pretend.call_recorder(lambda a: None),
                add=pretend.call_recorder(lambda a: None),
            ),
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            user=user,
            remote_addr=pretend.stub(),
        )
        journal_obj = pretend.stub()
        journal_cls = pretend.call_recorder(lambda **kw: journal_obj)

        get_user_role_in_project = pretend.call_recorder(
            lambda project, user, req: "Owner"
        )
        monkeypatch.setattr(views, "get_user_role_in_project", get_user_role_in_project)

        monkeypatch.setattr(views, "JournalEntry", journal_cls)
        send_removed_project_release_email = pretend.call_recorder(
            lambda req, contrib, **k: None
        )
        monkeypatch.setattr(
            views,
            "send_removed_project_release_email",
            send_removed_project_release_email,
        )

        view = views.ManageProjectRelease(release, request)

        result = view.delete_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert get_user_role_in_project.calls == [
            pretend.call(release.project, request.user, request),
            pretend.call(release.project, request.user, request),
        ]

        assert send_removed_project_release_email.calls == [
            pretend.call(
                request,
                request.user,
                release=release,
                submitter_name=request.user.username,
                submitter_role="Owner",
                recipient_role="Owner",
            )
        ]

        assert request.db.delete.calls == [pretend.call(release)]
        assert request.db.add.calls == [pretend.call(journal_obj)]
        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISALLOW_DELETION)
        ]
        assert journal_cls.calls == [
            pretend.call(
                name=release.project.name,
                action="remove release",
                version=release.version,
                submitted_by=request.user,
                submitted_from=request.remote_addr,
            )
        ]
        assert request.session.flash.calls == [
            pretend.call(f"Deleted release {release.version!r}", queue="success")
        ]
        assert request.route_path.calls == [
            pretend.call("manage.project.releases", project_name=release.project.name)
        ]
        assert release.project.record_event.calls == [
            pretend.call(
                tag="project:release:remove",
                ip_address=request.remote_addr,
                additional={
                    "submitted_by": request.user.username,
                    "canonical_version": release.canonical_version,
                },
            )
        ]

    def test_delete_project_release_no_confirm(self):
        release = pretend.stub(version="1.2.3", project=pretend.stub(name="foobar"))
        request = pretend.stub(
            POST={"confirm_delete_version": ""},
            method="POST",
            db=pretend.stub(delete=pretend.call_recorder(lambda a: None)),
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )
        view = views.ManageProjectRelease(release, request)

        result = view.delete_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert request.db.delete.calls == []
        assert request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]
        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISALLOW_DELETION)
        ]
        assert request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_delete_project_release_bad_confirm(self):
        release = pretend.stub(version="1.2.3", project=pretend.stub(name="foobar"))
        request = pretend.stub(
            POST={"confirm_delete_version": "invalid"},
            method="POST",
            db=pretend.stub(delete=pretend.call_recorder(lambda a: None)),
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )
        view = views.ManageProjectRelease(release, request)

        result = view.delete_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert request.db.delete.calls == []
        assert request.session.flash.calls == [
            pretend.call(
                "Could not delete release - "
                + f"'invalid' is not the same as {release.version!r}",
                queue="error",
            )
        ]
        assert request.route_path.calls == [
            pretend.call(
                "manage.project.release",
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_delete_project_release_file_disallow_deletion(self):
        release = pretend.stub(version="1.2.3", project=pretend.stub(name="foobar"))
        request = pretend.stub(
            method="POST",
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: True)),
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )
        view = views.ManageProjectRelease(release, request)

        result = view.delete_project_release_file()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISALLOW_DELETION)
        ]

        assert request.session.flash.calls == [
            pretend.call(
                (
                    "Project deletion temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
        ]
        assert request.route_path.calls == [
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
                submitted_from=db_request.remote_addr,
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

    def test_delete_project_release_file_no_confirm(self):
        release = pretend.stub(
            version="1.2.3",
            project=pretend.stub(name="foobar", normalized_name="foobar"),
        )
        request = pretend.stub(
            POST={"confirm_project_name": ""},
            method="POST",
            db=pretend.stub(delete=pretend.call_recorder(lambda a: None)),
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )
        view = views.ManageProjectRelease(release, request)

        result = view.delete_project_release_file()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert request.db.delete.calls == []
        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISALLOW_DELETION)
        ]
        assert request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]
        assert request.route_path.calls == [
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
    def organization(self, enable_organizations, pyramid_user):
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
            db_request.db.query(JournalEntry).options(joinedload("submitted_by")).one()
        )

        assert entry.name == project.name
        assert entry.action == "change Owner testuser to Maintainer"
        assert entry.submitted_by == db_request.user
        assert entry.submitted_from == db_request.remote_addr

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
            pretend.call("Removed role", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        entry = (
            db_request.db.query(JournalEntry).options(joinedload("submitted_by")).one()
        )

        assert entry.name == project.name
        assert entry.action == "remove Owner testuser"
        assert entry.submitted_by == db_request.user
        assert entry.submitted_from == db_request.remote_addr

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
            pretend.call("Cannot remove yourself as Owner", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

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


class TestChangeTeamProjectRole:
    @pytest.fixture
    def organization(self, enable_organizations, pyramid_user):
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

    def test_change_role(
        self,
        db_request,
        pyramid_user,
        organization_member,
        organization_team,
        organization_project,
        monkeypatch,
    ):
        role = TeamProjectRoleFactory.create(
            team=organization_team,
            project=organization_project,
            role_name=TeamProjectRoleType.Owner,
        )
        new_role_name = TeamProjectRoleType.Maintainer

        db_request.method = "POST"
        db_request.POST = MultiDict(
            {"role_id": role.id, "team_project_role_name": new_role_name}
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        send_team_collaborator_role_changed_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            views,
            "send_team_collaborator_role_changed_email",
            send_team_collaborator_role_changed_email,
        )
        send_role_changed_as_team_collaborator_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            views,
            "send_role_changed_as_team_collaborator_email",
            send_role_changed_as_team_collaborator_email,
        )

        result = views.change_team_project_role(organization_project, db_request)

        assert role.role_name == new_role_name
        assert db_request.route_path.calls == [
            pretend.call("manage.project.roles", project_name=organization_project.name)
        ]
        assert send_team_collaborator_role_changed_email.calls == [
            pretend.call(
                db_request,
                {pyramid_user},
                team=organization_team,
                submitter=pyramid_user,
                project_name=organization_project.name,
                role=new_role_name.value,
            )
        ]
        assert send_role_changed_as_team_collaborator_email.calls == [
            pretend.call(
                db_request,
                {organization_member},
                team=organization_team,
                submitter=pyramid_user,
                project_name=organization_project.name,
                role=new_role_name.value,
            )
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Changed permissions", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        entry = (
            db_request.db.query(JournalEntry).options(joinedload("submitted_by")).one()
        )

        assert entry.name == organization_project.name
        assert entry.action == f"change Owner {organization_team.name} to Maintainer"
        assert entry.submitted_by == db_request.user
        assert entry.submitted_from == db_request.remote_addr

    def test_change_role_invalid_role_name(self, pyramid_request, organization_project):
        pyramid_request.method = "POST"
        pyramid_request.POST = MultiDict(
            {
                "role_id": str(uuid.uuid4()),
                "team_project_role_name": "Invalid Role Name",
            }
        )
        pyramid_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )

        result = views.change_team_project_role(organization_project, pyramid_request)

        assert pyramid_request.route_path.calls == [
            pretend.call("manage.project.roles", project_name=organization_project.name)
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_change_missing_role(self, db_request, organization_project):
        missing_role_id = str(uuid.uuid4())

        db_request.method = "POST"
        db_request.POST = MultiDict(
            {"role_id": missing_role_id, "team_project_role_name": "Owner"}
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.change_team_project_role(organization_project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Could not find permissions", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_change_own_owner_role(
        self,
        db_request,
        organization_member,
        organization_team,
        organization_project,
    ):
        role = TeamProjectRoleFactory.create(
            team=organization_team,
            project=organization_project,
            role_name=TeamProjectRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.user = organization_member
        db_request.POST = MultiDict(
            {"role_id": role.id, "team_project_role_name": "Maintainer"}
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.change_team_project_role(organization_project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Cannot remove your own team as Owner", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"


class TestDeleteTeamProjectRole:
    @pytest.fixture
    def organization(self, enable_organizations, pyramid_user):
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

    def test_delete_role(
        self,
        db_request,
        organization_member,
        organization_team,
        organization_project,
        pyramid_user,
        monkeypatch,
    ):
        role = TeamProjectRoleFactory.create(
            team=organization_team,
            project=organization_project,
            role_name=TeamProjectRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        send_team_collaborator_removed_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            views,
            "send_team_collaborator_removed_email",
            send_team_collaborator_removed_email,
        )
        send_removed_as_team_collaborator_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            views,
            "send_removed_as_team_collaborator_email",
            send_removed_as_team_collaborator_email,
        )

        result = views.delete_team_project_role(organization_project, db_request)

        assert db_request.route_path.calls == [
            pretend.call("manage.project.roles", project_name=organization_project.name)
        ]
        assert db_request.db.query(TeamProjectRole).all() == []
        assert send_team_collaborator_removed_email.calls == [
            pretend.call(
                db_request,
                {pyramid_user},
                team=organization_team,
                submitter=pyramid_user,
                project_name=organization_project.name,
            )
        ]
        assert send_removed_as_team_collaborator_email.calls == [
            pretend.call(
                db_request,
                {organization_member},
                team=organization_team,
                submitter=pyramid_user,
                project_name=organization_project.name,
            )
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Removed permissions", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        entry = (
            db_request.db.query(JournalEntry).options(joinedload("submitted_by")).one()
        )

        assert entry.name == organization_project.name
        assert entry.action == f"remove Owner {organization_team.name}"
        assert entry.submitted_by == db_request.user
        assert entry.submitted_from == db_request.remote_addr

    def test_delete_missing_role(self, db_request, organization_project):
        missing_role_id = str(uuid.uuid4())

        db_request.method = "POST"
        db_request.POST = MultiDict({"role_id": missing_role_id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.delete_team_project_role(organization_project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Could not find permissions", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_delete_own_owner_role(
        self,
        db_request,
        organization_member,
        organization_team,
        organization_project,
    ):
        role = TeamProjectRoleFactory.create(
            team=organization_team,
            project=organization_project,
            role_name=TeamProjectRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.user = organization_member
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.delete_team_project_role(organization_project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Cannot remove your own team as Owner", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"


class TestManageProjectHistory:
    def test_get(self, db_request):
        project = ProjectFactory.create()
        older_event = ProjectEventFactory.create(
            source=project,
            tag="fake:event",
            ip_address="0.0.0.0",
            time=datetime.datetime(2017, 2, 5, 17, 18, 18, 462_634),
        )
        newer_event = ProjectEventFactory.create(
            source=project,
            tag="fake:event",
            ip_address="0.0.0.0",
            time=datetime.datetime(2018, 2, 5, 17, 18, 18, 462_634),
        )

        assert views.manage_project_history(project, db_request) == {
            "project": project,
            "events": [newer_event, older_event],
        }

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

    def test_first_page(self, db_request):
        page_number = 1
        params = MultiDict({"page": page_number})
        db_request.params = params

        project = ProjectFactory.create()
        items_per_page = 25
        total_items = items_per_page + 2
        for _ in range(total_items):
            ProjectEventFactory.create(
                source=project, tag="fake:event", ip_address="0.0.0.0"
            )
        events_query = (
            db_request.db.query(Project.Event)
            .join(Project.Event.source)
            .filter(Project.Event.source_id == project.id)
            .order_by(Project.Event.time.desc())
        )

        events_page = SQLAlchemyORMPage(
            events_query,
            page=page_number,
            items_per_page=items_per_page,
            item_count=total_items,
            url_maker=paginate_url_factory(db_request),
        )
        assert views.manage_project_history(project, db_request) == {
            "project": project,
            "events": events_page,
        }

    def test_last_page(self, db_request):
        page_number = 2
        params = MultiDict({"page": page_number})
        db_request.params = params

        project = ProjectFactory.create()
        items_per_page = 25
        total_items = items_per_page + 2
        for _ in range(total_items):
            ProjectEventFactory.create(
                source=project, tag="fake:event", ip_address="0.0.0.0"
            )
        events_query = (
            db_request.db.query(Project.Event)
            .join(Project.Event.source)
            .filter(Project.Event.source_id == project.id)
            .order_by(Project.Event.time.desc())
        )

        events_page = SQLAlchemyORMPage(
            events_query,
            page=page_number,
            items_per_page=items_per_page,
            item_count=total_items,
            url_maker=paginate_url_factory(db_request),
        )
        assert views.manage_project_history(project, db_request) == {
            "project": project,
            "events": events_page,
        }

    def test_raises_404_with_out_of_range_page(self, db_request):
        page_number = 3
        params = MultiDict({"page": page_number})
        db_request.params = params

        project = ProjectFactory.create()
        items_per_page = 25
        total_items = items_per_page + 2
        for _ in range(total_items):
            ProjectEventFactory.create(
                source=project, tag="fake:event", ip_address="0.0.0.0"
            )

        with pytest.raises(HTTPNotFound):
            assert views.manage_project_history(project, db_request)


class TestManageOIDCProviderViews:
    def test_initializes(self):
        metrics = pretend.stub()
        project = pretend.stub()
        request = pretend.stub(
            registry=pretend.stub(settings={"warehouse.oidc.enabled": True}),
            find_service=pretend.call_recorder(lambda *a, **kw: metrics),
        )
        view = views.ManageOIDCProviderViews(project, request)

        assert view.project is project
        assert view.request is request
        assert view.oidc_enabled
        assert view.metrics is metrics

        assert view.request.find_service.calls == [
            pretend.call(IMetricsService, context=None)
        ]

    @pytest.mark.parametrize(
        "ip_exceeded, user_exceeded",
        [
            (False, False),
            (False, True),
            (True, False),
        ],
    )
    def test_ratelimiting(self, ip_exceeded, user_exceeded):
        project = pretend.stub()

        metrics = pretend.stub()
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

            if name == "user_oidc.provider.register":
                return user_rate_limiter
            else:
                return ip_rate_limiter

        request = pretend.stub(
            registry=pretend.stub(settings={"warehouse.oidc.enabled": True}),
            find_service=pretend.call_recorder(find_service),
            user=pretend.stub(id=pretend.stub()),
            remote_addr=pretend.stub(),
        )

        view = views.ManageOIDCProviderViews(project, request)

        assert view._ratelimiters == {
            "user.oidc": user_rate_limiter,
            "ip.oidc": ip_rate_limiter,
        }
        assert request.find_service.calls == [
            pretend.call(IMetricsService, context=None),
            pretend.call(IRateLimiter, name="user_oidc.provider.register"),
            pretend.call(IRateLimiter, name="ip_oidc.provider.register"),
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

    def test_manage_project_oidc_providers(self, monkeypatch):
        project = pretend.stub()
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "warehouse.oidc.enabled": True,
                    "github.token": "fake-api-token",
                },
            ),
            find_service=lambda *a, **kw: None,
            flags=pretend.stub(enabled=pretend.call_recorder(lambda f: False)),
            POST=pretend.stub(),
        )

        github_provider_form_obj = pretend.stub()
        github_provider_form_cls = pretend.call_recorder(
            lambda *a, **kw: github_provider_form_obj
        )
        monkeypatch.setattr(views, "GitHubProviderForm", github_provider_form_cls)

        view = views.ManageOIDCProviderViews(project, request)
        assert view.manage_project_oidc_providers() == {
            "oidc_enabled": True,
            "project": project,
            "github_provider_form": github_provider_form_obj,
        }

        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISALLOW_OIDC)
        ]
        assert github_provider_form_cls.calls == [
            pretend.call(request.POST, api_token="fake-api-token")
        ]

    def test_manage_project_oidc_providers_admin_disabled(self, monkeypatch):
        project = pretend.stub()
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "warehouse.oidc.enabled": True,
                    "github.token": "fake-api-token",
                },
            ),
            find_service=lambda *a, **kw: None,
            flags=pretend.stub(enabled=pretend.call_recorder(lambda f: True)),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            POST=pretend.stub(),
        )

        view = views.ManageOIDCProviderViews(project, request)
        github_provider_form_obj = pretend.stub()
        github_provider_form_cls = pretend.call_recorder(
            lambda *a, **kw: github_provider_form_obj
        )
        monkeypatch.setattr(views, "GitHubProviderForm", github_provider_form_cls)

        view = views.ManageOIDCProviderViews(project, request)
        assert view.manage_project_oidc_providers() == {
            "oidc_enabled": True,
            "project": project,
            "github_provider_form": github_provider_form_obj,
        }

        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISALLOW_OIDC)
        ]
        assert request.session.flash.calls == [
            pretend.call(
                (
                    "OpenID Connect is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
        ]
        assert github_provider_form_cls.calls == [
            pretend.call(request.POST, api_token="fake-api-token")
        ]

    def test_manage_project_oidc_providers_oidc_not_enabled(self):
        project = pretend.stub()
        request = pretend.stub(
            registry=pretend.stub(settings={"warehouse.oidc.enabled": False}),
            find_service=lambda *a, **kw: None,
        )

        view = views.ManageOIDCProviderViews(project, request)

        with pytest.raises(HTTPNotFound):
            view.manage_project_oidc_providers()

    def test_add_github_oidc_provider_preexisting(self, monkeypatch):
        provider = pretend.stub(
            id="fakeid",
            provider_name="GitHub",
            repository_name="fakerepo",
            owner="fakeowner",
            owner_id="1234",
            workflow_filename="fakeworkflow.yml",
        )
        # NOTE: Can't set __str__ using pretend.stub()
        monkeypatch.setattr(provider.__class__, "__str__", lambda s: "fakespecifier")

        project = pretend.stub(
            name="fakeproject",
            oidc_providers=[],
            record_event=pretend.call_recorder(lambda *a, **kw: None),
            users=[],
        )

        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))

        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "warehouse.oidc.enabled": True,
                    "github.token": "fake-api-token",
                }
            ),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(enabled=pretend.call_recorder(lambda f: False)),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            POST=pretend.stub(),
            db=pretend.stub(
                query=lambda *a: pretend.stub(
                    filter=lambda *a: pretend.stub(one_or_none=lambda: provider)
                ),
                add=pretend.call_recorder(lambda o: None),
            ),
            remote_addr="0.0.0.0",
            path="request-path",
        )

        github_provider_form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            repository=pretend.stub(data=provider.repository_name),
            normalized_owner=provider.owner,
            workflow_filename=pretend.stub(data=provider.workflow_filename),
        )
        github_provider_form_cls = pretend.call_recorder(
            lambda *a, **kw: github_provider_form_obj
        )
        monkeypatch.setattr(views, "GitHubProviderForm", github_provider_form_cls)

        view = views.ManageOIDCProviderViews(project, request)
        monkeypatch.setattr(
            view, "_hit_ratelimits", pretend.call_recorder(lambda: None)
        )
        monkeypatch.setattr(
            view, "_check_ratelimits", pretend.call_recorder(lambda: None)
        )

        assert isinstance(view.add_github_oidc_provider(), HTTPSeeOther)
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_provider.attempt", tags=["provider:GitHub"]
            ),
            pretend.call("warehouse.oidc.add_provider.ok", tags=["provider:GitHub"]),
        ]
        assert project.record_event.calls == [
            pretend.call(
                tag="project:oidc:provider-added",
                ip_address=request.remote_addr,
                additional={
                    "provider": "GitHub",
                    "id": "fakeid",
                    "specifier": "fakespecifier",
                },
            )
        ]
        assert request.session.flash.calls == [
            pretend.call(
                "Added fakespecifier to fakeproject",
                queue="success",
            )
        ]
        assert request.db.add.calls == []
        assert github_provider_form_obj.validate.calls == [pretend.call()]
        assert view._hit_ratelimits.calls == [pretend.call()]
        assert view._check_ratelimits.calls == [pretend.call()]
        assert project.oidc_providers == [provider]

    def test_add_github_oidc_provider_created(self, monkeypatch):
        fakeusers = [pretend.stub(), pretend.stub(), pretend.stub()]
        project = pretend.stub(
            name="fakeproject",
            oidc_providers=[],
            record_event=pretend.call_recorder(lambda *a, **kw: None),
            users=fakeusers,
        )

        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))

        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "warehouse.oidc.enabled": True,
                    "github.token": "fake-api-token",
                }
            ),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(enabled=pretend.call_recorder(lambda f: False)),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            POST=pretend.stub(),
            db=pretend.stub(
                query=lambda *a: pretend.stub(
                    filter=lambda *a: pretend.stub(one_or_none=lambda: None)
                ),
                add=pretend.call_recorder(lambda o: setattr(o, "id", "fakeid")),
            ),
            remote_addr="0.0.0.0",
            path="request-path",
        )

        github_provider_form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            repository=pretend.stub(data="fakerepo"),
            normalized_owner="fakeowner",
            owner_id="1234",
            workflow_filename=pretend.stub(data="fakeworkflow.yml"),
        )
        github_provider_form_cls = pretend.call_recorder(
            lambda *a, **kw: github_provider_form_obj
        )
        monkeypatch.setattr(views, "GitHubProviderForm", github_provider_form_cls)
        monkeypatch.setattr(
            views,
            "send_oidc_provider_added_email",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        view = views.ManageOIDCProviderViews(project, request)
        monkeypatch.setattr(
            view, "_hit_ratelimits", pretend.call_recorder(lambda: None)
        )
        monkeypatch.setattr(
            view, "_check_ratelimits", pretend.call_recorder(lambda: None)
        )

        assert isinstance(view.add_github_oidc_provider(), HTTPSeeOther)
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_provider.attempt", tags=["provider:GitHub"]
            ),
            pretend.call("warehouse.oidc.add_provider.ok", tags=["provider:GitHub"]),
        ]
        assert project.record_event.calls == [
            pretend.call(
                tag="project:oidc:provider-added",
                ip_address=request.remote_addr,
                additional={
                    "provider": "GitHub",
                    "id": "fakeid",
                    "specifier": "fakeworkflow.yml @ fakeowner/fakerepo",
                },
            )
        ]
        assert request.session.flash.calls == [
            pretend.call(
                "Added fakeworkflow.yml @ fakeowner/fakerepo to fakeproject",
                queue="success",
            )
        ]
        assert request.db.add.calls == [pretend.call(project.oidc_providers[0])]
        assert github_provider_form_obj.validate.calls == [pretend.call()]
        assert views.send_oidc_provider_added_email.calls == [
            pretend.call(
                request,
                fakeuser,
                project_name="fakeproject",
                provider=project.oidc_providers[0],
            )
            for fakeuser in fakeusers
        ]
        assert view._hit_ratelimits.calls == [pretend.call()]
        assert view._check_ratelimits.calls == [pretend.call()]
        assert len(project.oidc_providers) == 1

    def test_add_github_oidc_provider_already_registered_with_project(
        self, monkeypatch
    ):
        provider = pretend.stub(
            id="fakeid",
            provider_name="GitHub",
            repository_name="fakerepo",
            owner="fakeowner",
            owner_id="1234",
            workflow_filename="fakeworkflow.yml",
        )
        # NOTE: Can't set __str__ using pretend.stub()
        monkeypatch.setattr(provider.__class__, "__str__", lambda s: "fakespecifier")

        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))

        project = pretend.stub(
            name="fakeproject",
            oidc_providers=[provider],
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )

        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "warehouse.oidc.enabled": True,
                    "github.token": "fake-api-token",
                }
            ),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(enabled=pretend.call_recorder(lambda f: False)),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            POST=pretend.stub(),
            db=pretend.stub(
                query=lambda *a: pretend.stub(
                    filter=lambda *a: pretend.stub(one_or_none=lambda: provider)
                ),
            ),
        )

        github_provider_form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            repository=pretend.stub(data=provider.repository_name),
            normalized_owner=provider.owner,
            workflow_filename=pretend.stub(data=provider.workflow_filename),
        )
        github_provider_form_cls = pretend.call_recorder(
            lambda *a, **kw: github_provider_form_obj
        )
        monkeypatch.setattr(views, "GitHubProviderForm", github_provider_form_cls)

        view = views.ManageOIDCProviderViews(project, request)
        monkeypatch.setattr(
            view, "_hit_ratelimits", pretend.call_recorder(lambda: None)
        )
        monkeypatch.setattr(
            view, "_check_ratelimits", pretend.call_recorder(lambda: None)
        )

        assert view.add_github_oidc_provider() == {
            "oidc_enabled": True,
            "project": project,
            "github_provider_form": github_provider_form_obj,
        }
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_provider.attempt", tags=["provider:GitHub"]
            ),
        ]
        assert project.record_event.calls == []
        assert request.session.flash.calls == [
            pretend.call(
                "fakespecifier is already registered with fakeproject",
                queue="error",
            )
        ]

    def test_add_github_oidc_provider_ratelimited(self, monkeypatch):
        project = pretend.stub()

        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))

        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "warehouse.oidc.enabled": True,
                }
            ),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(enabled=pretend.call_recorder(lambda f: False)),
            _=lambda s: s,
        )

        view = views.ManageOIDCProviderViews(project, request)
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

        assert view.add_github_oidc_provider().__class__ == HTTPTooManyRequests
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_provider.attempt", tags=["provider:GitHub"]
            ),
            pretend.call(
                "warehouse.oidc.add_provider.ratelimited", tags=["provider:GitHub"]
            ),
        ]

    def test_add_github_oidc_provider_oidc_not_enabled(self):
        project = pretend.stub()
        request = pretend.stub(
            registry=pretend.stub(settings={"warehouse.oidc.enabled": False}),
            find_service=lambda *a, **kw: None,
        )

        view = views.ManageOIDCProviderViews(project, request)

        with pytest.raises(HTTPNotFound):
            view.add_github_oidc_provider()

    def test_add_github_oidc_provider_admin_disabled(self, monkeypatch):
        project = pretend.stub()
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        request = pretend.stub(
            registry=pretend.stub(settings={"warehouse.oidc.enabled": True}),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(enabled=pretend.call_recorder(lambda f: True)),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            _=lambda s: s,
        )

        view = views.ManageOIDCProviderViews(project, request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            views.ManageOIDCProviderViews, "default_response", default_response
        )

        assert view.add_github_oidc_provider() == default_response
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_provider.attempt", tags=["provider:GitHub"]
            ),
        ]
        assert request.session.flash.calls == [
            pretend.call(
                (
                    "OpenID Connect is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
        ]

    def test_add_github_oidc_provider_invalid_form(self, monkeypatch):
        project = pretend.stub()
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        request = pretend.stub(
            registry=pretend.stub(settings={"warehouse.oidc.enabled": True}),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(enabled=pretend.call_recorder(lambda f: False)),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            _=lambda s: s,
        )

        github_provider_form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: False),
        )
        github_provider_form_cls = pretend.call_recorder(
            lambda *a, **kw: github_provider_form_obj
        )
        monkeypatch.setattr(views, "GitHubProviderForm", github_provider_form_cls)

        view = views.ManageOIDCProviderViews(project, request)
        default_response = {"github_provider_form": github_provider_form_obj}
        monkeypatch.setattr(
            views.ManageOIDCProviderViews, "default_response", default_response
        )
        monkeypatch.setattr(
            view, "_check_ratelimits", pretend.call_recorder(lambda: None)
        )
        monkeypatch.setattr(
            view, "_hit_ratelimits", pretend.call_recorder(lambda: None)
        )

        assert view.add_github_oidc_provider() == default_response
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_provider.attempt", tags=["provider:GitHub"]
            ),
        ]
        assert view._hit_ratelimits.calls == [pretend.call()]
        assert view._check_ratelimits.calls == [pretend.call()]
        assert github_provider_form_obj.validate.calls == [pretend.call()]

    def test_delete_oidc_provider(self, monkeypatch):
        provider = pretend.stub(
            provider_name="fakeprovider",
            id="fakeid",
        )
        # NOTE: Can't set __str__ using pretend.stub()
        monkeypatch.setattr(provider.__class__, "__str__", lambda s: "fakespecifier")

        fakeusers = [pretend.stub(), pretend.stub(), pretend.stub()]
        project = pretend.stub(
            oidc_providers=[provider],
            name="fakeproject",
            record_event=pretend.call_recorder(lambda *a, **kw: None),
            users=fakeusers,
        )
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        request = pretend.stub(
            registry=pretend.stub(settings={"warehouse.oidc.enabled": True}),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(enabled=pretend.call_recorder(lambda f: False)),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            POST=pretend.stub(),
            db=pretend.stub(
                query=lambda *a: pretend.stub(get=lambda id: provider),
            ),
            remote_addr="0.0.0.0",
            path="request-path",
        )

        delete_provider_form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            provider_id=pretend.stub(data="fakeid"),
        )
        delete_provider_form_cls = pretend.call_recorder(
            lambda *a, **kw: delete_provider_form_obj
        )
        monkeypatch.setattr(views, "DeleteProviderForm", delete_provider_form_cls)
        monkeypatch.setattr(
            views,
            "send_oidc_provider_removed_email",
            pretend.call_recorder(lambda *a, **kw: None),
        )

        view = views.ManageOIDCProviderViews(project, request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            views.ManageOIDCProviderViews, "default_response", default_response
        )

        assert isinstance(view.delete_oidc_provider(), HTTPSeeOther)
        assert provider not in project.oidc_providers

        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.delete_provider.attempt",
            ),
            pretend.call(
                "warehouse.oidc.delete_provider.ok", tags=["provider:fakeprovider"]
            ),
        ]

        assert project.record_event.calls == [
            pretend.call(
                tag="project:oidc:provider-removed",
                ip_address=request.remote_addr,
                additional={
                    "provider": "fakeprovider",
                    "id": "fakeid",
                    "specifier": "fakespecifier",
                },
            )
        ]

        assert request.flags.enabled.calls == [
            pretend.call(AdminFlagValue.DISALLOW_OIDC)
        ]
        assert request.session.flash.calls == [
            pretend.call("Removed fakespecifier from fakeproject", queue="success")
        ]

        assert delete_provider_form_cls.calls == [pretend.call(request.POST)]
        assert delete_provider_form_obj.validate.calls == [pretend.call()]

        assert views.send_oidc_provider_removed_email.calls == [
            pretend.call(
                request, fakeuser, project_name="fakeproject", provider=provider
            )
            for fakeuser in fakeusers
        ]

    def test_delete_oidc_provider_invalid_form(self, monkeypatch):
        provider = pretend.stub()
        project = pretend.stub(oidc_providers=[provider])
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        request = pretend.stub(
            registry=pretend.stub(settings={"warehouse.oidc.enabled": True}),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(enabled=pretend.call_recorder(lambda f: False)),
            POST=pretend.stub(),
        )

        delete_provider_form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: False),
        )
        delete_provider_form_cls = pretend.call_recorder(
            lambda *a, **kw: delete_provider_form_obj
        )
        monkeypatch.setattr(views, "DeleteProviderForm", delete_provider_form_cls)

        view = views.ManageOIDCProviderViews(project, request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            views.ManageOIDCProviderViews, "default_response", default_response
        )

        assert view.delete_oidc_provider() == default_response
        assert len(project.oidc_providers) == 1

        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.delete_provider.attempt",
            ),
        ]

        assert delete_provider_form_cls.calls == [pretend.call(request.POST)]
        assert delete_provider_form_obj.validate.calls == [pretend.call()]

    @pytest.mark.parametrize(
        "other_provider", [None, pretend.stub(id="different-fakeid")]
    )
    def test_delete_oidc_provider_not_found(self, monkeypatch, other_provider):
        provider = pretend.stub(
            provider_name="fakeprovider",
            id="fakeid",
        )
        # NOTE: Can't set __str__ using pretend.stub()
        monkeypatch.setattr(provider.__class__, "__str__", lambda s: "fakespecifier")

        project = pretend.stub(
            oidc_providers=[provider],
            name="fakeproject",
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        request = pretend.stub(
            registry=pretend.stub(settings={"warehouse.oidc.enabled": True}),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(enabled=pretend.call_recorder(lambda f: False)),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            POST=pretend.stub(),
            db=pretend.stub(
                query=lambda *a: pretend.stub(get=lambda id: other_provider),
            ),
            remote_addr="0.0.0.0",
        )

        delete_provider_form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            provider_id=pretend.stub(data="different-fakeid"),
        )
        delete_provider_form_cls = pretend.call_recorder(
            lambda *a, **kw: delete_provider_form_obj
        )
        monkeypatch.setattr(views, "DeleteProviderForm", delete_provider_form_cls)

        view = views.ManageOIDCProviderViews(project, request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            views.ManageOIDCProviderViews, "default_response", default_response
        )

        assert view.delete_oidc_provider() == default_response
        assert provider in project.oidc_providers  # not deleted
        assert other_provider not in project.oidc_providers

        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.delete_provider.attempt",
            ),
        ]

        assert project.record_event.calls == []
        assert request.session.flash.calls == [
            pretend.call("Invalid publisher for project", queue="error")
        ]

        assert delete_provider_form_cls.calls == [pretend.call(request.POST)]
        assert delete_provider_form_obj.validate.calls == [pretend.call()]

    def test_delete_oidc_provider_oidc_not_enabled(self):
        project = pretend.stub()
        request = pretend.stub(
            registry=pretend.stub(settings={"warehouse.oidc.enabled": False}),
            find_service=lambda *a, **kw: None,
        )

        view = views.ManageOIDCProviderViews(project, request)

        with pytest.raises(HTTPNotFound):
            view.delete_oidc_provider()

    def test_delete_oidc_provider_admin_disabled(self, monkeypatch):
        project = pretend.stub()
        metrics = pretend.stub(increment=pretend.call_recorder(lambda *a, **kw: None))
        request = pretend.stub(
            registry=pretend.stub(settings={"warehouse.oidc.enabled": True}),
            find_service=lambda *a, **kw: metrics,
            flags=pretend.stub(enabled=pretend.call_recorder(lambda f: True)),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
        )

        view = views.ManageOIDCProviderViews(project, request)
        default_response = {"_": pretend.stub()}
        monkeypatch.setattr(
            views.ManageOIDCProviderViews, "default_response", default_response
        )

        assert view.delete_oidc_provider() == default_response
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.delete_provider.attempt",
            ),
        ]
        assert request.session.flash.calls == [
            pretend.call(
                (
                    "OpenID Connect is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
        ]
