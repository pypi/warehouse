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

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from pyramid.response import Response
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound
from webob.multidict import MultiDict

import warehouse.utils.otp as otp

from warehouse.accounts.interfaces import IPasswordBreachedService, IUserService
from warehouse.admin.flags import AdminFlagValue
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.manage import views
from warehouse.packaging.models import (
    File,
    JournalEntry,
    Project,
    ProjectEvent,
    Role,
    User,
)
from warehouse.utils.paginate import paginate_url_factory
from warehouse.utils.project import remove_documentation

from ...common.db.accounts import EmailFactory
from ...common.db.packaging import (
    FileFactory,
    JournalEntryFactory,
    ProjectEventFactory,
    ProjectFactory,
    ReleaseFactory,
    RoleFactory,
    UserFactory,
)


class TestManageAccount:
    def test_default_response(self, monkeypatch):
        breach_service = pretend.stub()
        user_service = pretend.stub()
        name = pretend.stub()
        user_id = pretend.stub()
        request = pretend.stub(
            find_service=lambda iface, **kw: {
                IPasswordBreachedService: breach_service,
                IUserService: user_service,
            }[iface],
            user=pretend.stub(name=name, id=user_id),
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
        assert save_account_cls.calls == [pretend.call(name=name)]
        assert add_email_cls.calls == [
            pretend.call(user_id=user_id, user_service=user_service)
        ]
        assert change_pass_cls.calls == [
            pretend.call(user_service=user_service, breach_service=breach_service)
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
            POST={"name": "new name"},
            user=pretend.stub(id=pretend.stub(), name=pretend.stub()),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda *a, **kw: user_service,
        )
        save_account_obj = pretend.stub(validate=lambda: True, data=request.POST)
        monkeypatch.setattr(views, "SaveAccountForm", lambda *a, **kw: save_account_obj)
        monkeypatch.setattr(
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.save_account() == {
            **view.default_response,
            "save_account_form": save_account_obj,
        }
        assert request.session.flash.calls == [
            pretend.call("Account details updated", queue="success")
        ]
        assert update_user.calls == [pretend.call(request.user.id, **request.POST)]

    def test_save_account_validation_fails(self, monkeypatch):
        update_user = pretend.call_recorder(lambda *a, **kw: None)
        user_service = pretend.stub(update_user=update_user)
        request = pretend.stub(
            POST={"name": "new name"},
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

    def test_add_email(self, monkeypatch, pyramid_config):
        email_address = "test@example.com"
        email = pretend.stub(id=pretend.stub(), email=email_address)
        user_service = pretend.stub(
            add_email=pretend.call_recorder(lambda *a, **kw: email),
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        request = pretend.stub(
            POST={"email": email_address},
            db=pretend.stub(flush=lambda: None),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda a, **kw: user_service,
            user=pretend.stub(
                emails=[], username="username", name="Name", id=pretend.stub()
            ),
            task=pretend.call_recorder(lambda *args, **kwargs: send_email),
            remote_addr="0.0.0.0",
        )
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
        view = views.ManageAccountViews(request)

        assert view.add_email() == view.default_response
        assert user_service.add_email.calls == [
            pretend.call(request.user.id, email_address)
        ]
        assert request.session.flash.calls == [
            pretend.call(
                f"Email {email_address} added - check your email for "
                + "a verification link",
                queue="success",
            )
        ]
        assert send_email.calls == [pretend.call(request, (request.user, email))]
        assert user_service.record_event.calls == [
            pretend.call(
                request.user.id,
                tag="account:email:add",
                ip_address=request.remote_addr,
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
        )
        monkeypatch.setattr(
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.delete_email() == view.default_response
        assert request.session.flash.calls == [
            pretend.call(f"Email address {email.email} removed", queue="success")
        ]
        assert request.user.emails == [some_other_email]
        assert user_service.record_event.calls == [
            pretend.call(
                request.user.id,
                tag="account:email:remove",
                ip_address=request.remote_addr,
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
        db_request.remote_addr = "0.0.0.0"
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(db_request)

        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_primary_email_change_email", send_email)
        assert view.change_primary_email() == view.default_response
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
                ip_address=db_request.remote_addr,
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
        db_request.remote_addr = "0.0.0.0"
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(db_request)

        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_primary_email_change_email", send_email)
        assert view.change_primary_email() == view.default_response
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
                ip_address=db_request.remote_addr,
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
            pretend.call(f"Email address not found", queue="error")
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
            find_service=lambda *a, **kw: pretend.stub(),
            user=pretend.stub(id=pretend.stub(), username="username", name="Name"),
            remote_addr="0.0.0.0",
        )
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_email_verification_email", send_email)
        monkeypatch.setattr(
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.reverify_email() == view.default_response
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
        )
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_email_verification_email", send_email)
        monkeypatch.setattr(
            views.ManageAccountViews, "default_response", {"_": pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.reverify_email() == view.default_response
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
            remote_addr="0.0.0.0",
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

        assert view.change_password() == {
            **view.default_response,
            "change_password_form": change_pwd_obj,
        }
        assert request.session.flash.calls == [
            pretend.call("Password updated", queue="success")
        ]
        assert send_email.calls == [pretend.call(request, request.user)]
        assert user_service.update_user.calls == [
            pretend.call(request.user.id, password=new_password)
        ]
        assert user_service.record_event.calls == [
            pretend.call(
                request.user.id,
                tag="account:password:change",
                ip_address=request.remote_addr,
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
        db_request.params = {"confirm_username": user.username}
        db_request.find_service = lambda *a, **kw: pretend.stub()

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
            params={"confirm_username": ""},
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
            params={"confirm_username": "invalid"},
            user=pretend.stub(username="username"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda *a, **kw: pretend.stub(),
        )

        monkeypatch.setattr(
            views.ManageAccountViews, "default_response", pretend.stub()
        )

        view = views.ManageAccountViews(request)

        assert view.delete_account() == view.default_response
        assert request.session.flash.calls == [
            pretend.call(
                "Could not delete account - 'invalid' is not the same as " "'username'",
                queue="error",
            )
        ]

    def test_delete_account_has_active_projects(self, monkeypatch):
        request = pretend.stub(
            params={"confirm_username": "username"},
            user=pretend.stub(username="username"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda *a, **kw: pretend.stub(),
        )

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
        )

        view = views.ProvisionTOTPViews(request)
        result = view.generate_totp_qr()

        assert isinstance(result, Response)
        assert result.status_code == 403
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
            ),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        view = views.ProvisionTOTPViews(request)
        result = view.totp_provision()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar/"
        assert request.session.flash.calls == [
            pretend.call(
                "Account cannot be linked to more than one authentication "
                "application at a time",
                queue="error",
            )
        ]

    def test_totp_provision_two_factor_not_allowed(self):
        user_service = pretend.stub()
        request = pretend.stub(
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            find_service=lambda interface, **kw: {IUserService: user_service}[
                interface
            ],
            user=pretend.stub(has_primary_verified_email=False),
        )

        view = views.ProvisionTOTPViews(request)
        result = view.totp_provision()

        assert isinstance(result, Response)
        assert result.status_code == 403
        assert request.session.flash.calls == [
            pretend.call(
                "Verify your email to modify two factor authentication", queue="error"
            )
        ]

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
                ip_address=request.remote_addr,
                additional={"method": "totp"},
            )
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
        )

        view = views.ProvisionTOTPViews(request)
        result = view.validate_totp_provision()

        assert isinstance(result, Response)
        assert result.status_code == 403
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
            POST={"confirm_username": pretend.stub()},
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
                ip_address=request.remote_addr,
                additional={"method": "totp"},
            )
        ]

    def test_delete_totp_bad_username(self, monkeypatch, db_request):
        user_service = pretend.stub(
            get_totp_secret=lambda id: b"secret",
            update_user=pretend.call_recorder(lambda *a, **kw: None),
        )
        request = pretend.stub(
            POST={"confirm_username": pretend.stub()},
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
            pretend.call("Invalid credentials", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar/"

    def test_delete_totp_not_provisioned(self, monkeypatch, db_request):
        user_service = pretend.stub(
            get_totp_secret=lambda id: None,
            update_user=pretend.call_recorder(lambda *a, **kw: None),
        )
        request = pretend.stub(
            POST={"confirm_username": pretend.stub()},
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
        )

        view = views.ProvisionTOTPViews(request)
        result = view.delete_totp()

        assert isinstance(result, Response)
        assert result.status_code == 403
        assert request.session.flash.calls == [
            pretend.call(
                "Verify your email to modify two factor authentication", queue="error"
            )
        ]


class TestProvisionWebAuthn:
    def test_get_webauthn_view(self):
        user_service = pretend.stub()
        request = pretend.stub(find_service=lambda *a, **kw: user_service)

        view = views.ProvisionWebAuthnViews(request)
        result = view.webauthn_provision()

        assert result == {}

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
                public_key=b"fake_public_key",
                sign_count=1,
            ),
            label=pretend.stub(data="fake_label"),
        )
        provision_webauthn_cls = pretend.call_recorder(
            lambda *a, **kw: provision_webauthn_obj
        )
        monkeypatch.setattr(views, "ProvisionWebAuthnForm", provision_webauthn_cls)

        view = views.ProvisionWebAuthnViews(request)
        result = view.validate_webauthn_provision()

        assert request.session.get_webauthn_challenge.calls == [pretend.call()]
        assert request.session.clear_webauthn_challenge.calls == [pretend.call()]
        assert user_service.add_webauthn.calls == [
            pretend.call(
                1234,
                label="fake_label",
                credential_id="fake_credential_id",
                public_key="fake_public_key",
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
                ip_address=request.remote_addr,
                additional={
                    "method": "webauthn",
                    "label": provision_webauthn_obj.label.data,
                },
            )
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
                ip_address=request.remote_addr,
                additional={
                    "method": "webauthn",
                    "label": delete_webauthn_obj.label.data,
                },
            )
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
        all_projects = [pretend.stub()]
        monkeypatch.setattr(
            views.ProvisionMacaroonViews, "project_names", project_names
        )
        monkeypatch.setattr(
            views.ProvisionMacaroonViews, "all_projects", all_projects
        )

        request = pretend.stub(
            user=pretend.stub(id=pretend.stub()),
            find_service=lambda interface, **kw: {
                IMacaroonService: pretend.stub(),
                IUserService: pretend.stub(),
            }[interface],
        )

        view = views.ProvisionMacaroonViews(request)

        assert view.default_response == {
            "project_names": project_names,
            "all_projects": all_projects,
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
        all_projects = [pretend.stub()]
        monkeypatch.setattr(
            views.ProvisionMacaroonViews, "project_names", project_names
        )
        monkeypatch.setattr(
            views.ProvisionMacaroonViews, "all_projects", all_projects
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
            user=pretend.stub(id=pretend.stub(), has_primary_verified_email=True),
            find_service=lambda interface, **kw: {
                IMacaroonService: macaroon_service,
                IUserService: user_service,
            }[interface],
            remote_addr="0.0.0.0",
        )

        create_macaroon_obj = pretend.stub(
            validate=lambda: True,
            description=pretend.stub(data=pretend.stub()),
            validated_scope="foobar",
        )
        create_macaroon_cls = pretend.call_recorder(
            lambda *a, **kw: create_macaroon_obj
        )
        monkeypatch.setattr(views, "CreateMacaroonForm", create_macaroon_cls)

        project_names = [pretend.stub()]
        all_projects = [pretend.stub()]
        monkeypatch.setattr(
            views.ProvisionMacaroonViews, "project_names", project_names
        )
        monkeypatch.setattr(
            views.ProvisionMacaroonViews, "all_projects", all_projects
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
                caveats={
                    "permissions": create_macaroon_obj.validated_scope,
                    "version": 1,
                },
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
                ip_address=request.remote_addr,
                additional={
                    "description": create_macaroon_obj.description.data,
                    "caveats": {
                        "permissions": create_macaroon_obj.validated_scope,
                        "version": 1,
                    },
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
        record_event = pretend.call_recorder(lambda *a, **kw: None)
        user_service = pretend.stub(record_event=record_event)
        request = pretend.stub(
            POST={},
            domain=pretend.stub(),
            user=pretend.stub(
                id=pretend.stub(),
                has_primary_verified_email=True,
                username=pretend.stub(),
                projects=[
                    pretend.stub(normalized_name="foo", record_event=record_event),
                    pretend.stub(normalized_name="bar", record_event=record_event),
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
                caveats={
                    "permissions": create_macaroon_obj.validated_scope,
                    "version": 1,
                },
            )
        ]
        assert result == {
            **default_response,
            "serialized_macaroon": "not a real raw macaroon",
            "macaroon": macaroon,
            "create_macaroon_form": create_macaroon_obj,
        }
        assert record_event.calls == [
            pretend.call(
                request.user.id,
                tag="account:api_token:added",
                ip_address=request.remote_addr,
                additional={
                    "description": create_macaroon_obj.description.data,
                    "caveats": {
                        "permissions": create_macaroon_obj.validated_scope,
                        "version": 1,
                    },
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
            POST={},
            route_path=pretend.call_recorder(lambda x: pretend.stub()),
            find_service=lambda interface, **kw: {
                IMacaroonService: macaroon_service,
                IUserService: pretend.stub(),
            }[interface],
            referer="/fake/safe/route",
            host=None,
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

    def test_delete_macaroon_dangerous_redirect(self, monkeypatch):
        macaroon_service = pretend.stub(
            delete_macaroon=pretend.call_recorder(lambda id: pretend.stub())
        )
        request = pretend.stub(
            POST={},
            route_path=pretend.call_recorder(lambda x: "/safe/route"),
            find_service=lambda interface, **kw: {
                IMacaroonService: macaroon_service,
                IUserService: pretend.stub(),
            }[interface],
            referer="http://google.com/",
            host=None,
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
        macaroon = pretend.stub(
            description="fake macaroon", caveats={"version": 1, "permissions": "user"}
        )
        macaroon_service = pretend.stub(
            delete_macaroon=pretend.call_recorder(lambda id: pretend.stub()),
            find_macaroon=pretend.call_recorder(lambda id: macaroon),
        )
        record_event = pretend.call_recorder(
            pretend.call_recorder(lambda *a, **kw: None)
        )
        user_service = pretend.stub(record_event=record_event)
        request = pretend.stub(
            POST={},
            route_path=pretend.call_recorder(lambda x: pretend.stub()),
            find_service=lambda interface, **kw: {
                IMacaroonService: macaroon_service,
                IUserService: user_service,
            }[interface],
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            referer="/fake/safe/route",
            host=None,
            user=pretend.stub(id=pretend.stub()),
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
                ip_address=request.remote_addr,
                additional={"macaroon_id": delete_macaroon_obj.macaroon_id.data},
            )
        ]

    def test_delete_macaroon_records_events_for_each_project(self, monkeypatch):
        macaroon = pretend.stub(
            description="fake macaroon",
            caveats={"version": 1, "permissions": {"projects": ["foo", "bar"]}},
        )
        macaroon_service = pretend.stub(
            delete_macaroon=pretend.call_recorder(lambda id: pretend.stub()),
            find_macaroon=pretend.call_recorder(lambda id: macaroon),
        )
        record_event = pretend.call_recorder(
            pretend.call_recorder(lambda *a, **kw: None)
        )
        user_service = pretend.stub(record_event=record_event)
        request = pretend.stub(
            POST={},
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
                    pretend.stub(normalized_name="foo", record_event=record_event),
                    pretend.stub(normalized_name="bar", record_event=record_event),
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
        assert record_event.calls == [
            pretend.call(
                request.user.id,
                tag="account:api_token:removed",
                ip_address=request.remote_addr,
                additional={"macaroon_id": delete_macaroon_obj.macaroon_id.data},
            ),
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
        db_request.user = UserFactory(
            projects=[
                project_with_older_release,
                project_with_newer_release,
                newer_project_with_no_releases,
                older_project_with_no_releases,
            ]
        )
        user_second_owner = UserFactory(
            projects=[project_with_older_release, older_project_with_no_releases]
        )
        RoleFactory.create(user=db_request.user, project=project_with_newer_release)
        RoleFactory.create(user=db_request.user, project=newer_project_with_no_releases)
        RoleFactory.create(user=user_second_owner, project=project_with_newer_release)

        assert views.manage_projects(db_request) == {
            "projects": [
                newer_project_with_no_releases,
                project_with_newer_release,
                older_project_with_no_releases,
                project_with_older_release,
            ],
            "projects_owned": {
                project_with_newer_release.name,
                newer_project_with_no_releases.name,
            },
            "projects_sole_owned": {newer_project_with_no_releases.name},
        }


class TestManageProjectSettings:
    def test_manage_project_settings(self):
        request = pretend.stub()
        project = pretend.stub()

        assert views.manage_project_settings(project, request) == {"project": project}

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
        project = pretend.stub(normalized_name="foo")
        request = pretend.stub(
            POST={"confirm_project_name": "bar"},
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
                "Could not delete project - 'bar' is not the same as 'foo'",
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

    def test_delete_project(self, db_request):
        project = ProjectFactory.create(name="foo")

        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST["confirm_project_name"] = project.normalized_name
        db_request.user = UserFactory.create()
        db_request.remote_addr = "192.168.1.1"

        result = views.delete_project(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Deleted the project 'foo'", queue="success")
        ]
        assert db_request.route_path.calls == [pretend.call("manage.projects")]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
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
        project = pretend.stub(normalized_name="foo")
        request = pretend.stub(
            POST={"confirm_project_name": "bar"},
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        with pytest.raises(HTTPSeeOther) as exc:
            views.destroy_project_docs(project, request)
            assert exc.value.status_code == 303
            assert exc.value.headers["Location"] == "/foo/bar/"

        assert request.session.flash.calls == [
            pretend.call(
                "Could not delete project - 'bar' is not the same as 'foo'",
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
        db_request.POST["confirm_project_name"] = project.normalized_name
        db_request.user = UserFactory.create()
        db_request.remote_addr = "192.168.1.1"
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
        release = pretend.stub(project=project, files=pretend.stub(all=lambda: files))
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

    def test_delete_project_release(self, monkeypatch):
        release = pretend.stub(
            version="1.2.3",
            canonical_version="1.2.3",
            project=pretend.stub(
                name="foobar", record_event=pretend.call_recorder(lambda *a, **kw: None)
            ),
        )
        request = pretend.stub(
            POST={"confirm_version": release.version},
            method="POST",
            db=pretend.stub(
                delete=pretend.call_recorder(lambda a: None),
                add=pretend.call_recorder(lambda a: None),
            ),
            flags=pretend.stub(enabled=pretend.call_recorder(lambda *a: False)),
            route_path=pretend.call_recorder(lambda *a, **kw: "/the-redirect"),
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            user=pretend.stub(username=pretend.stub()),
            remote_addr=pretend.stub(),
        )
        journal_obj = pretend.stub()
        journal_cls = pretend.call_recorder(lambda **kw: journal_obj)
        monkeypatch.setattr(views, "JournalEntry", journal_cls)

        view = views.ManageProjectRelease(release, request)

        result = view.delete_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

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
            POST={"confirm_version": ""},
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
            POST={"confirm_version": "invalid"},
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

    def test_delete_project_release_file(self, db_request):
        user = UserFactory.create()

        project = ProjectFactory.create(name="foobar")
        release = ReleaseFactory.create(project=project)
        release_file = FileFactory.create(
            release=release, filename=f"foobar-{release.version}.tar.gz"
        )

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
        db_request.remote_addr = "1.2.3.4"

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
                submitted_from="1.2.3.4",
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

    def test_delete_project_release_file_no_confirm(self):
        release = pretend.stub(version="1.2.3", project=pretend.stub(name="foobar"))
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
    def test_get_manage_project_roles(self, db_request):
        user_service = pretend.stub()
        db_request.find_service = pretend.call_recorder(
            lambda iface, context: user_service
        )
        form_obj = pretend.stub()
        form_class = pretend.call_recorder(lambda d, user_service: form_obj)

        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create()
        role = RoleFactory.create(user=user, project=project)

        result = views.manage_project_roles(project, db_request, _form_class=form_class)

        assert db_request.find_service.calls == [
            pretend.call(IUserService, context=None)
        ]
        assert form_class.calls == [
            pretend.call(db_request.POST, user_service=user_service)
        ]
        assert result == {
            "project": project,
            "roles_by_user": {user.username: [role]},
            "form": form_obj,
        }

    def test_post_new_role_validation_fails(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = RoleFactory.create(user=user, project=project)

        user_service = pretend.stub()
        db_request.find_service = pretend.call_recorder(
            lambda iface, context: user_service
        )
        db_request.method = "POST"
        form_obj = pretend.stub(validate=pretend.call_recorder(lambda: False))
        form_class = pretend.call_recorder(lambda d, user_service: form_obj)

        result = views.manage_project_roles(project, db_request, _form_class=form_class)

        assert db_request.find_service.calls == [
            pretend.call(IUserService, context=None)
        ]
        assert form_class.calls == [
            pretend.call(db_request.POST, user_service=user_service)
        ]
        assert form_obj.validate.calls == [pretend.call()]
        assert result == {
            "project": project,
            "roles_by_user": {user.username: [role]},
            "form": form_obj,
        }

    def test_post_new_role(self, monkeypatch, db_request):
        project = ProjectFactory.create(name="foobar")
        new_user = UserFactory.create(username="new_user")
        EmailFactory.create(user=new_user, verified=True, primary=True)
        owner_1 = UserFactory.create(username="owner_1")
        owner_2 = UserFactory.create(username="owner_2")
        owner_1_role = RoleFactory.create(
            user=owner_1, project=project, role_name="Owner"
        )
        owner_2_role = RoleFactory.create(
            user=owner_2, project=project, role_name="Owner"
        )

        user_service = pretend.stub(
            find_userid=lambda username: new_user.id, get_user=lambda userid: new_user
        )
        db_request.find_service = pretend.call_recorder(
            lambda iface, context: user_service
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

        send_collaborator_added_email = pretend.call_recorder(lambda r, u, **k: None)
        monkeypatch.setattr(
            views, "send_collaborator_added_email", send_collaborator_added_email
        )

        send_added_as_collaborator_email = pretend.call_recorder(lambda r, u, **k: None)
        monkeypatch.setattr(
            views, "send_added_as_collaborator_email", send_added_as_collaborator_email
        )

        result = views.manage_project_roles(project, db_request, _form_class=form_class)

        assert db_request.find_service.calls == [
            pretend.call(IUserService, context=None)
        ]
        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(db_request.POST, user_service=user_service),
            pretend.call(user_service=user_service),
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Added collaborator 'new_user'", queue="success")
        ]

        assert send_collaborator_added_email.calls == [
            pretend.call(
                db_request,
                {owner_2},
                user=new_user,
                submitter=db_request.user,
                project_name=project.name,
                role=form_obj.role_name.data,
            )
        ]

        assert send_added_as_collaborator_email.calls == [
            pretend.call(
                db_request,
                new_user,
                submitter=db_request.user,
                project_name=project.name,
                role=form_obj.role_name.data,
            )
        ]

        # Only one role is created
        role = db_request.db.query(Role).filter(Role.user == new_user).one()

        assert result == {
            "project": project,
            "roles_by_user": {
                new_user.username: [role],
                owner_1.username: [owner_1_role],
                owner_2.username: [owner_2_role],
            },
            "form": form_obj,
        }

        entry = (
            db_request.db.query(JournalEntry).options(joinedload("submitted_by")).one()
        )

        assert entry.name == project.name
        assert entry.action == "add Owner new_user"
        assert entry.submitted_by == db_request.user
        assert entry.submitted_from == db_request.remote_addr

    def test_post_duplicate_role(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = RoleFactory.create(user=user, project=project, role_name="Owner")

        user_service = pretend.stub(
            find_userid=lambda username: user.id, get_user=lambda userid: user
        )
        db_request.find_service = pretend.call_recorder(
            lambda iface, context: user_service
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
            pretend.call(IUserService, context=None)
        ]
        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(db_request.POST, user_service=user_service),
            pretend.call(user_service=user_service),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "User 'testuser' already has Owner role for project", queue="error"
            )
        ]

        # No additional roles are created
        assert role == db_request.db.query(Role).one()

        assert result == {
            "project": project,
            "roles_by_user": {user.username: [role]},
            "form": form_obj,
        }

    @pytest.mark.parametrize("with_email", [True, False])
    def test_post_unverified_email(self, db_request, with_email):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        if with_email:
            EmailFactory.create(user=user, verified=False, primary=True)

        user_service = pretend.stub(
            find_userid=lambda username: user.id, get_user=lambda userid: user
        )
        db_request.find_service = pretend.call_recorder(
            lambda iface, context: user_service
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
            pretend.call(IUserService, context=None)
        ]
        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(db_request.POST, user_service=user_service),
            pretend.call(user_service=user_service),
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

        assert result == {"project": project, "roles_by_user": {}, "form": form_obj}


class TestChangeProjectRoles:
    def test_change_role(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = RoleFactory.create(user=user, project=project, role_name="Owner")
        new_role_name = "Maintainer"

        db_request.method = "POST"
        db_request.user = UserFactory.create()
        db_request.remote_addr = "10.10.10.10"
        db_request.POST = MultiDict({"role_id": role.id, "role_name": new_role_name})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.change_project_role(project, db_request)

        assert role.role_name == new_role_name
        assert db_request.route_path.calls == [
            pretend.call("manage.project.roles", project_name=project.name)
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

    def test_change_role_when_multiple(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        owner_role = RoleFactory.create(user=user, project=project, role_name="Owner")
        maintainer_role = RoleFactory.create(
            user=user, project=project, role_name="Maintainer"
        )
        new_role_name = "Maintainer"

        db_request.method = "POST"
        db_request.user = UserFactory.create()
        db_request.remote_addr = "10.10.10.10"
        db_request.POST = MultiDict(
            [
                ("role_id", owner_role.id),
                ("role_id", maintainer_role.id),
                ("role_name", new_role_name),
            ]
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.change_project_role(project, db_request)

        assert db_request.db.query(Role).all() == [maintainer_role]
        assert db_request.route_path.calls == [
            pretend.call("manage.project.roles", project_name=project.name)
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
        assert entry.action == "remove Owner testuser"
        assert entry.submitted_by == db_request.user
        assert entry.submitted_from == db_request.remote_addr

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

    def test_change_own_owner_role_when_multiple(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        owner_role = RoleFactory.create(user=user, project=project, role_name="Owner")
        maintainer_role = RoleFactory.create(
            user=user, project=project, role_name="Maintainer"
        )

        db_request.method = "POST"
        db_request.user = user
        db_request.POST = MultiDict(
            [
                ("role_id", owner_role.id),
                ("role_id", maintainer_role.id),
                ("role_name", "Maintainer"),
            ]
        )
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


class TestDeleteProjectRoles:
    def test_delete_role(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = RoleFactory.create(user=user, project=project, role_name="Owner")

        db_request.method = "POST"
        db_request.user = UserFactory.create()
        db_request.remote_addr = "10.10.10.10"
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = views.delete_project_role(project, db_request)

        assert db_request.route_path.calls == [
            pretend.call("manage.project.roles", project_name=project.name)
        ]
        assert db_request.db.query(Role).all() == []
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


class TestManageProjectHistory:
    def test_get(self, db_request):
        project = ProjectFactory.create()
        older_event = ProjectEventFactory.create(
            project=project,
            tag="fake:event",
            ip_address="0.0.0.0",
            time=datetime.datetime(2017, 2, 5, 17, 18, 18, 462_634),
        )
        newer_event = ProjectEventFactory.create(
            project=project,
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
                project=project, tag="fake:event", ip_address="0.0.0.0"
            )
        events_query = (
            db_request.db.query(ProjectEvent)
            .join(ProjectEvent.project)
            .filter(ProjectEvent.project_id == project.id)
            .order_by(ProjectEvent.time.desc())
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
                project=project, tag="fake:event", ip_address="0.0.0.0"
            )
        events_query = (
            db_request.db.query(ProjectEvent)
            .join(ProjectEvent.project)
            .filter(ProjectEvent.project_id == project.id)
            .order_by(ProjectEvent.time.desc())
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
                project=project, tag="fake:event", ip_address="0.0.0.0"
            )

        with pytest.raises(HTTPNotFound):
            assert views.manage_project_history(project, db_request)


class TestManageProjectJournal:
    def test_get(self, db_request):
        project = ProjectFactory.create()
        older_journal = JournalEntryFactory.create(
            name=project.name,
            submitted_date=datetime.datetime(2017, 2, 5, 17, 18, 18, 462_634),
        )
        newer_journal = JournalEntryFactory.create(
            name=project.name,
            submitted_date=datetime.datetime(2018, 2, 5, 17, 18, 18, 462_634),
        )

        assert views.manage_project_journal(project, db_request) == {
            "project": project,
            "journals": [newer_journal, older_journal],
        }

    def test_raises_400_with_pagenum_type_str(self, monkeypatch, db_request):
        params = MultiDict({"page": "abc"})
        db_request.params = params

        journals_query = pretend.stub()
        db_request.journals_query = pretend.stub(
            journals_query=lambda *a, **kw: journals_query
        )

        page_obj = pretend.stub(page_count=10, item_count=1000)
        page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
        monkeypatch.setattr(views, "SQLAlchemyORMPage", page_cls)

        url_maker = pretend.stub()
        url_maker_factory = pretend.call_recorder(lambda request: url_maker)
        monkeypatch.setattr(views, "paginate_url_factory", url_maker_factory)

        project = ProjectFactory.create()
        with pytest.raises(HTTPBadRequest):
            views.manage_project_journal(project, db_request)

        assert page_cls.calls == []

    def test_first_page(self, db_request):
        page_number = 1
        params = MultiDict({"page": page_number})
        db_request.params = params

        project = ProjectFactory.create()
        items_per_page = 25
        total_items = items_per_page + 2
        for _ in range(total_items):
            JournalEntryFactory.create(
                name=project.name, submitted_date=datetime.datetime.now()
            )
        journals_query = (
            db_request.db.query(JournalEntry)
            .options(joinedload("submitted_by"))
            .filter(JournalEntry.name == project.name)
            .order_by(JournalEntry.submitted_date.desc(), JournalEntry.id.desc())
        )

        journals_page = SQLAlchemyORMPage(
            journals_query,
            page=page_number,
            items_per_page=items_per_page,
            item_count=total_items,
            url_maker=paginate_url_factory(db_request),
        )
        assert views.manage_project_journal(project, db_request) == {
            "project": project,
            "journals": journals_page,
        }

    def test_last_page(self, db_request):
        page_number = 2
        params = MultiDict({"page": page_number})
        db_request.params = params

        project = ProjectFactory.create()
        items_per_page = 25
        total_items = items_per_page + 2
        for _ in range(total_items):
            JournalEntryFactory.create(
                name=project.name, submitted_date=datetime.datetime.now()
            )
        journals_query = (
            db_request.db.query(JournalEntry)
            .options(joinedload("submitted_by"))
            .filter(JournalEntry.name == project.name)
            .order_by(JournalEntry.submitted_date.desc(), JournalEntry.id.desc())
        )

        journals_page = SQLAlchemyORMPage(
            journals_query,
            page=page_number,
            items_per_page=items_per_page,
            item_count=total_items,
            url_maker=paginate_url_factory(db_request),
        )
        assert views.manage_project_journal(project, db_request) == {
            "project": project,
            "journals": journals_page,
        }

    def test_raises_404_with_out_of_range_page(self, db_request):
        page_number = 3
        params = MultiDict({"page": page_number})
        db_request.params = params

        project = ProjectFactory.create()
        items_per_page = 25
        total_items = items_per_page + 2
        for _ in range(total_items):
            JournalEntryFactory.create(
                name=project.name, submitted_date=datetime.datetime.now()
            )

        with pytest.raises(HTTPNotFound):
            assert views.manage_project_journal(project, db_request)
