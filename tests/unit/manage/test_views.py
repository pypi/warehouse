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

import datetime
import uuid

import pretend
import pytest

from pyramid.httpexceptions import HTTPSeeOther
from sqlalchemy.orm.exc import NoResultFound
from webob.multidict import MultiDict

from warehouse.manage import views
from warehouse.accounts.interfaces import IUserService
from warehouse.packaging.models import JournalEntry, Project, Role, User
from warehouse.utils.project import remove_documentation

from ...common.db.accounts import EmailFactory
from ...common.db.packaging import (
    JournalEntryFactory, ProjectFactory, ReleaseFactory, RoleFactory,
    UserFactory,
)


class TestManageAccount:

    def test_default_response(self, monkeypatch):
        user_service = pretend.stub()
        name = pretend.stub()
        request = pretend.stub(
            find_service=lambda *a, **kw: user_service,
            user=pretend.stub(name=name),
        )
        save_account_obj = pretend.stub()
        save_account_cls = pretend.call_recorder(lambda **kw: save_account_obj)
        monkeypatch.setattr(views, 'SaveAccountForm', save_account_cls)

        add_email_obj = pretend.stub()
        add_email_cls = pretend.call_recorder(lambda **kw: add_email_obj)
        monkeypatch.setattr(views, 'AddEmailForm', add_email_cls)

        change_pass_obj = pretend.stub()
        change_pass_cls = pretend.call_recorder(lambda **kw: change_pass_obj)
        monkeypatch.setattr(views, 'ChangePasswordForm', change_pass_cls)

        view = views.ManageAccountViews(request)

        monkeypatch.setattr(
            views.ManageAccountViews, 'active_projects', pretend.stub()
        )

        assert view.default_response == {
            'save_account_form': save_account_obj,
            'add_email_form': add_email_obj,
            'change_password_form': change_pass_obj,
            'active_projects': view.active_projects,
        }
        assert view.request == request
        assert view.user_service == user_service
        assert save_account_cls.calls == [
            pretend.call(name=name),
        ]
        assert add_email_cls.calls == [
            pretend.call(user_service=user_service),
        ]
        assert change_pass_cls.calls == [
            pretend.call(user_service=user_service),
        ]

    def test_active_projects(self, db_request):
        user = UserFactory.create()
        another_user = UserFactory.create()

        db_request.user = user
        db_request.find_service = lambda *a, **kw: pretend.stub()

        # A project with a sole owner that is the user
        with_sole_owner = ProjectFactory.create()
        RoleFactory.create(
            user=user, project=with_sole_owner, role_name='Owner'
        )
        RoleFactory.create(
            user=another_user, project=with_sole_owner, role_name='Maintainer'
        )

        # A project with multiple owners, including the user
        with_multiple_owners = ProjectFactory.create()
        RoleFactory.create(
            user=user, project=with_multiple_owners, role_name='Owner'
        )
        RoleFactory.create(
            user=another_user, project=with_multiple_owners, role_name='Owner'
        )

        # A project with a sole owner that is not the user
        not_an_owner = ProjectFactory.create()
        RoleFactory.create(
            user=user, project=not_an_owner, role_name='Maintatiner'
        )
        RoleFactory.create(
            user=another_user, project=not_an_owner, role_name='Owner'
        )

        view = views.ManageAccountViews(db_request)

        assert view.active_projects == [with_sole_owner]

    def test_manage_account(self, monkeypatch):
        user_service = pretend.stub()
        name = pretend.stub()
        request = pretend.stub(
            find_service=lambda *a, **kw: user_service,
            user=pretend.stub(name=name),
        )
        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', {'_': pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.manage_account() == view.default_response
        assert view.request == request
        assert view.user_service == user_service

    def test_save_account(self, monkeypatch):
        update_user = pretend.call_recorder(lambda *a, **kw: None)
        user_service = pretend.stub(update_user=update_user)
        request = pretend.stub(
            POST={'name': 'new name'},
            user=pretend.stub(id=pretend.stub(), name=pretend.stub()),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            find_service=lambda *a, **kw: user_service,
        )
        save_account_obj = pretend.stub(
            validate=lambda: True, data=request.POST
        )
        monkeypatch.setattr(
            views, 'SaveAccountForm', lambda *a, **kw: save_account_obj
        )
        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', {'_': pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.save_account() == {
            **view.default_response,
            'save_account_form': save_account_obj,
        }
        assert request.session.flash.calls == [
            pretend.call('Account details updated', queue='success'),
        ]
        assert update_user.calls == [
            pretend.call(request.user.id, **request.POST)
        ]

    def test_save_account_validation_fails(self, monkeypatch):
        update_user = pretend.call_recorder(lambda *a, **kw: None)
        user_service = pretend.stub(update_user=update_user)
        request = pretend.stub(
            POST={'name': 'new name'},
            user=pretend.stub(id=pretend.stub(), name=pretend.stub()),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            find_service=lambda *a, **kw: user_service,
        )
        save_account_obj = pretend.stub(validate=lambda: False)
        monkeypatch.setattr(
            views, 'SaveAccountForm', lambda *a, **kw: save_account_obj
        )
        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', {'_': pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.save_account() == {
            **view.default_response,
            'save_account_form': save_account_obj,
        }
        assert request.session.flash.calls == []
        assert update_user.calls == []

    def test_add_email(self, monkeypatch, pyramid_config):
        email_address = "test@example.com"
        email = pretend.stub(id=pretend.stub(), email=email_address)
        user_service = pretend.stub(
            add_email=pretend.call_recorder(lambda *a, **kw: email)
        )
        request = pretend.stub(
            POST={'email': email_address},
            db=pretend.stub(flush=lambda: None),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            find_service=lambda a, **kw: user_service,
            user=pretend.stub(
                emails=[], username="username", name="Name", id=pretend.stub()
            ),
            task=pretend.call_recorder(lambda *args, **kwargs: send_email),
        )
        monkeypatch.setattr(
            views, 'AddEmailForm', lambda *a, **kw: pretend.stub(
                validate=lambda: True,
                email=pretend.stub(data=email_address),
            )
        )

        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, 'send_email_verification_email', send_email)

        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', {'_': pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.add_email() == view.default_response
        assert user_service.add_email.calls == [
            pretend.call(request.user.id, email_address)
        ]
        assert request.session.flash.calls == [
            pretend.call(
                f'Email {email_address} added - check your email for ' +
                'a verification link',
                queue='success',
            ),
        ]
        assert send_email.calls == [
            pretend.call(request, request.user, email),
        ]

    def test_add_email_validation_fails(self, monkeypatch):
        email_address = "test@example.com"
        request = pretend.stub(
            POST={'email': email_address},
            db=pretend.stub(flush=lambda: None),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            find_service=lambda a, **kw: pretend.stub(),
            user=pretend.stub(emails=[], name=pretend.stub()),
        )
        add_email_obj = pretend.stub(
            validate=lambda: False,
            email=pretend.stub(data=email_address),
        )
        add_email_cls = pretend.call_recorder(lambda *a, **kw: add_email_obj)
        monkeypatch.setattr(views, 'AddEmailForm', add_email_cls)

        email_obj = pretend.stub(id=pretend.stub(), email=email_address)
        email_cls = pretend.call_recorder(lambda **kw: email_obj)
        monkeypatch.setattr(views, 'Email', email_cls)

        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', {'_': pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.add_email() == {
            **view.default_response,
            'add_email_form': add_email_obj,
        }
        assert request.user.emails == []
        assert email_cls.calls == []
        assert request.session.flash.calls == []

    def test_delete_email(self, monkeypatch):
        email = pretend.stub(
            id=pretend.stub(), primary=False, email=pretend.stub(),
        )
        some_other_email = pretend.stub()
        request = pretend.stub(
            POST={'delete_email_id': email.id},
            user=pretend.stub(
                id=pretend.stub(),
                emails=[email, some_other_email],
                name=pretend.stub(),
            ),
            db=pretend.stub(
                query=lambda a: pretend.stub(
                    filter=lambda *a: pretend.stub(one=lambda: email)
                ),
            ),
            find_service=lambda *a, **kw: pretend.stub(),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            )
        )
        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', {'_': pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.delete_email() == view.default_response
        assert request.session.flash.calls == [
            pretend.call(
                f'Email address {email.email} removed', queue='success'
            )
        ]
        assert request.user.emails == [some_other_email]

    def test_delete_email_not_found(self, monkeypatch):
        email = pretend.stub()

        def raise_no_result():
            raise NoResultFound

        request = pretend.stub(
            POST={'delete_email_id': 'missing_id'},
            user=pretend.stub(
                id=pretend.stub(),
                emails=[email],
                name=pretend.stub(),
            ),
            db=pretend.stub(
                query=lambda a: pretend.stub(
                    filter=lambda *a: pretend.stub(one=raise_no_result)
                ),
            ),
            find_service=lambda *a, **kw: pretend.stub(),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            )
        )
        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', {'_': pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.delete_email() == view.default_response
        assert request.session.flash.calls == [
            pretend.call('Email address not found', queue='error'),
        ]
        assert request.user.emails == [email]

    def test_delete_email_is_primary(self, monkeypatch):
        email = pretend.stub(primary=True)

        request = pretend.stub(
            POST={'delete_email_id': 'missing_id'},
            user=pretend.stub(
                id=pretend.stub(),
                emails=[email],
                name=pretend.stub(),
            ),
            db=pretend.stub(
                query=lambda a: pretend.stub(
                    filter=lambda *a: pretend.stub(one=lambda: email)
                ),
            ),
            find_service=lambda *a, **kw: pretend.stub(),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            )
        )
        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', {'_': pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.delete_email() == view.default_response
        assert request.session.flash.calls == [
            pretend.call(
                'Cannot remove primary email address', queue='error'
            ),
        ]
        assert request.user.emails == [email]

    def test_change_primary_email(self, monkeypatch, db_request):
        user = UserFactory()
        old_primary = EmailFactory(primary=True, user=user)
        new_primary = EmailFactory(primary=False, verified=True, user=user)

        db_request.user = user

        db_request.find_service = lambda *a, **kw: pretend.stub()
        db_request.POST = {'primary_email_id': new_primary.id}
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', {'_': pretend.stub()}
        )
        view = views.ManageAccountViews(db_request)

        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(
            views, 'send_primary_email_change_email', send_email
        )
        assert view.change_primary_email() == view.default_response
        assert send_email.calls == [
            pretend.call(db_request, db_request.user, old_primary.email)
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                f'Email address {new_primary.email} set as primary',
                queue='success',
            )
        ]
        assert not old_primary.primary
        assert new_primary.primary

    def test_change_primary_email_not_found(self, monkeypatch, db_request):
        user = UserFactory()
        old_primary = EmailFactory(primary=True, user=user)
        missing_email_id = 9999

        db_request.user = user
        db_request.find_service = lambda *a, **kw: pretend.stub()
        db_request.POST = {'primary_email_id': missing_email_id}
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', {'_': pretend.stub()}
        )
        view = views.ManageAccountViews(db_request)

        assert view.change_primary_email() == view.default_response
        assert db_request.session.flash.calls == [
            pretend.call(f'Email address not found', queue='error')
        ]
        assert old_primary.primary

    def test_reverify_email(self, monkeypatch):
        email = pretend.stub(verified=False, email='email_address')

        request = pretend.stub(
            POST={'reverify_email_id': pretend.stub()},
            db=pretend.stub(
                query=lambda *a: pretend.stub(
                    filter=lambda *a: pretend.stub(one=lambda: email)
                ),
            ),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None)
            ),
            find_service=lambda *a, **kw: pretend.stub(),
            user=pretend.stub(
                id=pretend.stub(),
                username="username",
                name="Name",
            ),
        )
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, 'send_email_verification_email', send_email)
        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', {'_': pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.reverify_email() == view.default_response
        assert request.session.flash.calls == [
            pretend.call(
                'Verification email for email_address resent',
                queue='success',
            ),
        ]
        assert send_email.calls == [pretend.call(request, request.user, email)]

    def test_reverify_email_not_found(self, monkeypatch):
        def raise_no_result():
            raise NoResultFound

        request = pretend.stub(
            POST={'reverify_email_id': pretend.stub()},
            db=pretend.stub(
                query=lambda *a: pretend.stub(
                    filter=lambda *a: pretend.stub(one=raise_no_result)
                ),
            ),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None)
            ),
            find_service=lambda *a, **kw: pretend.stub(),
            user=pretend.stub(id=pretend.stub()),
        )
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, 'send_email_verification_email', send_email)
        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', {'_': pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.reverify_email() == view.default_response
        assert request.session.flash.calls == [
            pretend.call('Email address not found', queue='error'),
        ]
        assert send_email.calls == []

    def test_reverify_email_already_verified(self, monkeypatch):
        email = pretend.stub(verified=True, email='email_address')

        request = pretend.stub(
            POST={'reverify_email_id': pretend.stub()},
            db=pretend.stub(
                query=lambda *a: pretend.stub(
                    filter=lambda *a: pretend.stub(one=lambda: email)
                ),
            ),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None)
            ),
            find_service=lambda *a, **kw: pretend.stub(),
            user=pretend.stub(id=pretend.stub()),
        )
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, 'send_email_verification_email', send_email)
        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', {'_': pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.reverify_email() == view.default_response
        assert request.session.flash.calls == [
            pretend.call('Email is already verified', queue='error'),
        ]
        assert send_email.calls == []

    def test_change_password(self, monkeypatch):
        old_password = '0ld_p455w0rd'
        new_password = 'n3w_p455w0rd'
        user_service = pretend.stub(
            update_user=pretend.call_recorder(lambda *a, **kw: None)
        )
        request = pretend.stub(
            POST={
                'password': old_password,
                'new_password': new_password,
                'password_confirm': new_password,
            },
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None)
            ),
            find_service=lambda *a, **kw: user_service,
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                email=pretend.stub(),
                name=pretend.stub(),
            ),
        )
        change_pwd_obj = pretend.stub(
            validate=lambda: True,
            new_password=pretend.stub(data=new_password),
        )
        change_pwd_cls = pretend.call_recorder(lambda *a, **kw: change_pwd_obj)
        monkeypatch.setattr(views, 'ChangePasswordForm', change_pwd_cls)

        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, 'send_password_change_email', send_email)
        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', {'_': pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.change_password() == {
            **view.default_response,
            'change_password_form': change_pwd_obj,
        }
        assert request.session.flash.calls == [
            pretend.call('Password updated', queue='success'),
        ]
        assert send_email.calls == [pretend.call(request, request.user)]
        assert user_service.update_user.calls == [
            pretend.call(request.user.id, password=new_password),
        ]

    def test_change_password_validation_fails(self, monkeypatch):
        old_password = '0ld_p455w0rd'
        new_password = 'n3w_p455w0rd'
        user_service = pretend.stub(
            update_user=pretend.call_recorder(lambda *a, **kw: None)
        )
        request = pretend.stub(
            POST={
                'password': old_password,
                'new_password': new_password,
                'password_confirm': new_password,
            },
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None)
            ),
            find_service=lambda *a, **kw: user_service,
            user=pretend.stub(
                id=pretend.stub(),
                username=pretend.stub(),
                email=pretend.stub(),
                name=pretend.stub(),
            ),
        )
        change_pwd_obj = pretend.stub(
            validate=lambda: False,
            new_password=pretend.stub(data=new_password),
        )
        change_pwd_cls = pretend.call_recorder(lambda *a, **kw: change_pwd_obj)
        monkeypatch.setattr(views, 'ChangePasswordForm', change_pwd_cls)

        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, 'send_password_change_email', send_email)
        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', {'_': pretend.stub()}
        )
        view = views.ManageAccountViews(request)

        assert view.change_password() == {
            **view.default_response,
            'change_password_form': change_pwd_obj,
        }
        assert request.session.flash.calls == []
        assert send_email.calls == []
        assert user_service.update_user.calls == []

    def test_delete_account(self, monkeypatch, db_request):
        user = UserFactory.create()
        deleted_user = UserFactory.create(username='deleted-user')
        journal = JournalEntryFactory(submitted_by=user)

        db_request.user = user
        db_request.params = {'confirm_username': user.username}
        db_request.find_service = lambda *a, **kw: pretend.stub()

        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', pretend.stub()
        )
        monkeypatch.setattr(views.ManageAccountViews, 'active_projects', [])
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, 'send_account_deletion_email', send_email)
        logout_response = pretend.stub()
        logout = pretend.call_recorder(lambda *a: logout_response)
        monkeypatch.setattr(views, 'logout', logout)

        view = views.ManageAccountViews(db_request)

        assert view.delete_account() == logout_response
        assert journal.submitted_by == deleted_user
        assert db_request.db.query(User).all() == [deleted_user]
        assert send_email.calls == [pretend.call(db_request, user)]
        assert logout.calls == [pretend.call(db_request)]

    def test_delete_account_no_confirm(self, monkeypatch):
        request = pretend.stub(
            params={'confirm_username': ''},
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            find_service=lambda *a, **kw: pretend.stub(),
        )

        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', pretend.stub()
        )

        view = views.ManageAccountViews(request)

        assert view.delete_account() == view.default_response
        assert request.session.flash.calls == [
            pretend.call('Must confirm the request', queue='error')
        ]

    def test_delete_account_wrong_confirm(self, monkeypatch):
        request = pretend.stub(
            params={'confirm_username': 'invalid'},
            user=pretend.stub(username='username'),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            find_service=lambda *a, **kw: pretend.stub(),
        )

        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', pretend.stub()
        )

        view = views.ManageAccountViews(request)

        assert view.delete_account() == view.default_response
        assert request.session.flash.calls == [
            pretend.call(
                "Could not delete account - 'invalid' is not the same as "
                "'username'",
                queue='error',
            )
        ]

    def test_delete_account_has_active_projects(self, monkeypatch):
        request = pretend.stub(
            params={'confirm_username': 'username'},
            user=pretend.stub(username='username'),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            find_service=lambda *a, **kw: pretend.stub(),
        )

        monkeypatch.setattr(
            views.ManageAccountViews, 'default_response', pretend.stub()
        )
        monkeypatch.setattr(
            views.ManageAccountViews, 'active_projects', [pretend.stub()]
        )

        view = views.ManageAccountViews(request)

        assert view.delete_account() == view.default_response
        assert request.session.flash.calls == [
            pretend.call(
                "Cannot delete account with active project ownerships",
                queue='error',
            )
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
            ],
        )
        RoleFactory.create(
            user=db_request.user,
            project=project_with_newer_release,
        )

        assert views.manage_projects(db_request) == {
            'projects': [
                newer_project_with_no_releases,
                project_with_newer_release,
                older_project_with_no_releases,
                project_with_older_release,
            ],
            'projects_owned': {project_with_newer_release.name},
        }


class TestManageProjectSettings:

    def test_manage_project_settings(self):
        request = pretend.stub()
        project = pretend.stub()

        assert views.manage_project_settings(project, request) == {
            "project": project,
        }

    def test_delete_project_no_confirm(self):
        project = pretend.stub(normalized_name='foo')
        request = pretend.stub(
            POST={},
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        with pytest.raises(HTTPSeeOther) as exc:
            views.delete_project(project, request)
            assert exc.value.status_code == 303
            assert exc.value.headers["Location"] == "/foo/bar/"

        assert request.session.flash.calls == [
            pretend.call("Must confirm the request", queue="error"),
        ]

    def test_delete_project_wrong_confirm(self):
        project = pretend.stub(normalized_name='foo')
        request = pretend.stub(
            POST={"confirm_project_name": "bar"},
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        with pytest.raises(HTTPSeeOther) as exc:
            views.delete_project(project, request)
            assert exc.value.status_code == 303
            assert exc.value.headers["Location"] == "/foo/bar/"

        assert request.session.flash.calls == [
            pretend.call(
                "Could not delete project - 'bar' is not the same as 'foo'",
                queue="error"
            ),
        ]

    def test_delete_project(self, db_request):
        project = ProjectFactory.create(name="foo")

        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )
        db_request.POST["confirm_project_name"] = project.normalized_name
        db_request.user = UserFactory.create()
        db_request.remote_addr = "192.168.1.1"

        result = views.delete_project(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                "Successfully deleted the project 'foo'",
                queue="success"
            ),
        ]
        assert db_request.route_path.calls == [
            pretend.call('manage.projects'),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert not (db_request.db.query(Project)
                                 .filter(Project.name == "foo").count())


class TestManageProjectDocumentation:

    def test_manage_project_documentation(self):
        request = pretend.stub()
        project = pretend.stub()

        assert views.manage_project_documentation(project, request) == {
            "project": project,
        }

    def test_destroy_project_docs_no_confirm(self):
        project = pretend.stub(normalized_name='foo')
        request = pretend.stub(
            POST={},
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        with pytest.raises(HTTPSeeOther) as exc:
            views.destroy_project_docs(project, request)
            assert exc.value.status_code == 303
            assert exc.value.headers["Location"] == "/foo/bar/"

        assert request.session.flash.calls == [
            pretend.call("Must confirm the request", queue="error"),
        ]

    def test_destroy_project_docs_wrong_confirm(self):
        project = pretend.stub(normalized_name='foo')
        request = pretend.stub(
            POST={"confirm_project_name": "bar"},
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            route_path=lambda *a, **kw: "/foo/bar/",
        )

        with pytest.raises(HTTPSeeOther) as exc:
            views.destroy_project_docs(project, request)
            assert exc.value.status_code == 303
            assert exc.value.headers["Location"] == "/foo/bar/"

        assert request.session.flash.calls == [
            pretend.call(
                "Could not delete project - 'bar' is not the same as 'foo'",
                queue="error"
            ),
        ]

    def test_destroy_project_docs(self, db_request):
        project = ProjectFactory.create(name="foo")
        remove_documentation_recorder = pretend.stub(
            delay=pretend.call_recorder(
                lambda *a, **kw: None
            )
        )
        task = pretend.call_recorder(
            lambda *a, **kw: remove_documentation_recorder
        )

        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )
        db_request.POST["confirm_project_name"] = project.normalized_name
        db_request.user = UserFactory.create()
        db_request.remote_addr = "192.168.1.1"
        db_request.task = task

        result = views.destroy_project_docs(project, db_request)

        assert task.calls == [
            pretend.call(remove_documentation)
        ]

        assert remove_documentation_recorder.delay.calls == [
            pretend.call(project.name)
        ]

        assert db_request.session.flash.calls == [
            pretend.call(
                "Successfully deleted docs for project 'foo'",
                queue="success"
            ),
        ]
        assert db_request.route_path.calls == [
            pretend.call('manage.project.documentation', project_name='foo'),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
        assert not (db_request.db.query(Project)
                                 .filter(Project.name == "foo")
                                 .first().has_docs)


class TestManageProjectReleases:

    def test_manage_project_releases(self):
        request = pretend.stub()
        project = pretend.stub()

        assert views.manage_project_releases(project, request) == {
            "project": project,
        }


class TestManageProjectRelease:

    def test_manage_project_release(self):
        files = pretend.stub()
        project = pretend.stub()
        release = pretend.stub(
            project=project,
            files=pretend.stub(all=lambda: files),
        )
        request = pretend.stub()
        view = views.ManageProjectRelease(release, request)

        assert view.manage_project_release() == {
            'project': project,
            'release': release,
            'files': files,
        }

    def test_delete_project_release(self, monkeypatch):
        release = pretend.stub(
            version='1.2.3',
            project=pretend.stub(name='foobar'),
        )
        request = pretend.stub(
            POST={'confirm_version': release.version},
            method="POST",
            db=pretend.stub(
                delete=pretend.call_recorder(lambda a: None),
                add=pretend.call_recorder(lambda a: None),
            ),
            route_path=pretend.call_recorder(lambda *a, **kw: '/the-redirect'),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None)
            ),
            user=pretend.stub(),
            remote_addr=pretend.stub(),
        )
        journal_obj = pretend.stub()
        journal_cls = pretend.call_recorder(lambda **kw: journal_obj)
        monkeypatch.setattr(views, 'JournalEntry', journal_cls)

        view = views.ManageProjectRelease(release, request)

        result = view.delete_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert request.db.delete.calls == [pretend.call(release)]
        assert request.db.add.calls == [pretend.call(journal_obj)]
        assert journal_cls.calls == [
            pretend.call(
                name=release.project.name,
                action="remove release",
                version=release.version,
                submitted_by=request.user,
                submitted_from=request.remote_addr,
            ),
        ]
        assert request.session.flash.calls == [
            pretend.call(
                f"Successfully deleted release {release.version!r}",
                queue="success",
            )
        ]
        assert request.route_path.calls == [
            pretend.call(
                'manage.project.releases',
                project_name=release.project.name,
            )
        ]

    def test_delete_project_release_no_confirm(self):
        release = pretend.stub(
            version='1.2.3',
            project=pretend.stub(name='foobar'),
        )
        request = pretend.stub(
            POST={'confirm_version': ''},
            method="POST",
            db=pretend.stub(delete=pretend.call_recorder(lambda a: None)),
            route_path=pretend.call_recorder(lambda *a, **kw: '/the-redirect'),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None)
            ),
        )
        view = views.ManageProjectRelease(release, request)

        result = view.delete_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert request.db.delete.calls == []
        assert request.session.flash.calls == [
            pretend.call(
                "Must confirm the request", queue='error'
            )
        ]
        assert request.route_path.calls == [
            pretend.call(
                'manage.project.release',
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_delete_project_release_bad_confirm(self):
        release = pretend.stub(
            version='1.2.3',
            project=pretend.stub(name='foobar'),
        )
        request = pretend.stub(
            POST={'confirm_version': 'invalid'},
            method="POST",
            db=pretend.stub(delete=pretend.call_recorder(lambda a: None)),
            route_path=pretend.call_recorder(lambda *a, **kw: '/the-redirect'),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None)
            ),
        )
        view = views.ManageProjectRelease(release, request)

        result = view.delete_project_release()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert request.db.delete.calls == []
        assert request.session.flash.calls == [
            pretend.call(
                "Could not delete release - " +
                f"'invalid' is not the same as {release.version!r}",
                queue="error",
            )
        ]
        assert request.route_path.calls == [
            pretend.call(
                'manage.project.release',
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_delete_project_release_file(self, monkeypatch):
        release_file = pretend.stub(
            filename='foo-bar.tar.gz',
            id=str(uuid.uuid4()),
        )
        release = pretend.stub(
            version='1.2.3',
            project=pretend.stub(name='foobar'),
        )
        request = pretend.stub(
            POST={
                'confirm_project_name': release.project.name,
                'file_id': release_file.id,
            },
            method="POST",
            db=pretend.stub(
                delete=pretend.call_recorder(lambda a: None),
                add=pretend.call_recorder(lambda a: None),
                query=lambda a: pretend.stub(
                    filter=lambda *a: pretend.stub(one=lambda: release_file),
                ),
            ),
            route_path=pretend.call_recorder(lambda *a, **kw: '/the-redirect'),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None)
            ),
            user=pretend.stub(),
            remote_addr=pretend.stub(),
        )
        journal_obj = pretend.stub()
        journal_cls = pretend.call_recorder(lambda **kw: journal_obj)
        monkeypatch.setattr(views, 'JournalEntry', journal_cls)

        view = views.ManageProjectRelease(release, request)

        result = view.delete_project_release_file()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert request.session.flash.calls == [
            pretend.call(
                f"Successfully deleted file {release_file.filename!r}",
                queue="success",
            )
        ]
        assert request.db.delete.calls == [pretend.call(release_file)]
        assert request.db.add.calls == [pretend.call(journal_obj)]
        assert journal_cls.calls == [
            pretend.call(
                name=release.project.name,
                action=f"remove file {release_file.filename}",
                version=release.version,
                submitted_by=request.user,
                submitted_from=request.remote_addr,
            ),
        ]
        assert request.route_path.calls == [
            pretend.call(
                'manage.project.release',
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_delete_project_release_file_no_confirm(self):
        release = pretend.stub(
            version='1.2.3',
            project=pretend.stub(name='foobar'),
        )
        request = pretend.stub(
            POST={'confirm_project_name': ''},
            method="POST",
            db=pretend.stub(delete=pretend.call_recorder(lambda a: None)),
            route_path=pretend.call_recorder(lambda *a, **kw: '/the-redirect'),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None)
            ),
        )
        view = views.ManageProjectRelease(release, request)

        result = view.delete_project_release_file()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert request.db.delete.calls == []
        assert request.session.flash.calls == [
            pretend.call(
                "Must confirm the request", queue='error'
            )
        ]
        assert request.route_path.calls == [
            pretend.call(
                'manage.project.release',
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_delete_project_release_file_not_found(self):
        release = pretend.stub(
            version='1.2.3',
            project=pretend.stub(name='foobar'),
        )

        def no_result_found():
            raise NoResultFound

        request = pretend.stub(
            POST={'confirm_project_name': 'whatever'},
            method="POST",
            db=pretend.stub(
                delete=pretend.call_recorder(lambda a: None),
                query=lambda a: pretend.stub(
                    filter=lambda *a: pretend.stub(one=no_result_found),
                ),
            ),
            route_path=pretend.call_recorder(lambda *a, **kw: '/the-redirect'),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None)
            ),
        )
        view = views.ManageProjectRelease(release, request)

        result = view.delete_project_release_file()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert request.db.delete.calls == []
        assert request.session.flash.calls == [
            pretend.call(
                "Could not find file", queue='error'
            )
        ]
        assert request.route_path.calls == [
            pretend.call(
                'manage.project.release',
                project_name=release.project.name,
                version=release.version,
            )
        ]

    def test_delete_project_release_file_bad_confirm(self):
        release_file = pretend.stub(
            filename='foo-bar.tar.gz',
            id=str(uuid.uuid4()),
        )
        release = pretend.stub(
            version='1.2.3',
            project=pretend.stub(name='foobar'),
        )
        request = pretend.stub(
            POST={'confirm_project_name': 'invalid'},
            method="POST",
            db=pretend.stub(
                delete=pretend.call_recorder(lambda a: None),
                query=lambda a: pretend.stub(
                    filter=lambda *a: pretend.stub(one=lambda: release_file),
                ),
            ),
            route_path=pretend.call_recorder(lambda *a, **kw: '/the-redirect'),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None)
            ),
        )
        view = views.ManageProjectRelease(release, request)

        result = view.delete_project_release_file()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        assert request.db.delete.calls == []
        assert request.session.flash.calls == [
            pretend.call(
                "Could not delete file - " +
                f"'invalid' is not the same as {release.project.name!r}",
                queue="error",
            )
        ]
        assert request.route_path.calls == [
            pretend.call(
                'manage.project.release',
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

        result = views.manage_project_roles(
            project, db_request, _form_class=form_class
        )

        assert db_request.find_service.calls == [
            pretend.call(IUserService, context=None),
        ]
        assert form_class.calls == [
            pretend.call(db_request.POST, user_service=user_service),
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

        result = views.manage_project_roles(
            project, db_request, _form_class=form_class
        )

        assert db_request.find_service.calls == [
            pretend.call(IUserService, context=None),
        ]
        assert form_class.calls == [
            pretend.call(db_request.POST, user_service=user_service),
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
        owner_1 = UserFactory.create(username="owner_1")
        owner_2 = UserFactory.create(username="owner_2")
        owner_1_role = RoleFactory.create(
            user=owner_1, project=project, role_name="Owner"
        )
        owner_2_role = RoleFactory.create(
            user=owner_2, project=project, role_name="Owner"
        )

        user_service = pretend.stub(
            find_userid=lambda username: new_user.id,
            get_user=lambda userid: new_user,
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
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )

        send_collaborator_added_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(
            views,
            'send_collaborator_added_email',
            send_collaborator_added_email,
        )

        send_added_as_collaborator_email = pretend.call_recorder(
            lambda *a: None)
        monkeypatch.setattr(
            views,
            'send_added_as_collaborator_email',
            send_added_as_collaborator_email,
        )

        result = views.manage_project_roles(
            project, db_request, _form_class=form_class
        )

        assert db_request.find_service.calls == [
            pretend.call(IUserService, context=None),
        ]
        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(db_request.POST, user_service=user_service),
            pretend.call(user_service=user_service),
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Added collaborator 'new_user'", queue="success"),
        ]

        assert send_collaborator_added_email.calls == [
            pretend.call(
                db_request,
                new_user,
                db_request.user,
                project.name,
                form_obj.role_name.data,
                {owner_2}
            )
        ]

        assert send_added_as_collaborator_email.calls == [
            pretend.call(
                db_request,
                db_request.user,
                project.name,
                form_obj.role_name.data,
                new_user,
            ),
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

        entry = db_request.db.query(JournalEntry).one()

        assert entry.name == project.name
        assert entry.action == "add Owner new_user"
        assert entry.submitted_by == db_request.user
        assert entry.submitted_from == db_request.remote_addr

    def test_post_duplicate_role(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = RoleFactory.create(
            user=user, project=project, role_name="Owner"
        )

        user_service = pretend.stub(
            find_userid=lambda username: user.id,
            get_user=lambda userid: user,
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
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )

        result = views.manage_project_roles(
            project, db_request, _form_class=form_class
        )

        assert db_request.find_service.calls == [
            pretend.call(IUserService, context=None),
        ]
        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(db_request.POST, user_service=user_service),
            pretend.call(user_service=user_service),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "User 'testuser' already has Owner role for project",
                queue="error",
            ),
        ]

        # No additional roles are created
        assert role == db_request.db.query(Role).one()

        assert result == {
            "project": project,
            "roles_by_user": {user.username: [role]},
            "form": form_obj,
        }


class TestChangeProjectRoles:

    def test_change_role(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = RoleFactory.create(
            user=user, project=project, role_name="Owner"
        )
        new_role_name = "Maintainer"

        db_request.method = "POST"
        db_request.user = UserFactory.create()
        db_request.remote_addr = "10.10.10.10"
        db_request.POST = MultiDict({
            "role_id": role.id,
            "role_name": new_role_name,
        })
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )

        result = views.change_project_role(project, db_request)

        assert role.role_name == new_role_name
        assert db_request.route_path.calls == [
            pretend.call('manage.project.roles', project_name=project.name),
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Successfully changed role", queue="success"),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        entry = db_request.db.query(JournalEntry).one()

        assert entry.name == project.name
        assert entry.action == "change Owner testuser to Maintainer"
        assert entry.submitted_by == db_request.user
        assert entry.submitted_from == db_request.remote_addr

    def test_change_role_invalid_role_name(self, pyramid_request):
        project = pretend.stub(name="foobar")

        pyramid_request.method = "POST"
        pyramid_request.POST = MultiDict({
            "role_id": str(uuid.uuid4()),
            "role_name": "Invalid Role Name",
        })
        pyramid_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )

        result = views.change_project_role(project, pyramid_request)

        assert pyramid_request.route_path.calls == [
            pretend.call('manage.project.roles', project_name=project.name),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_change_role_when_multiple(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        owner_role = RoleFactory.create(
            user=user, project=project, role_name="Owner"
        )
        maintainer_role = RoleFactory.create(
            user=user, project=project, role_name="Maintainer"
        )
        new_role_name = "Maintainer"

        db_request.method = "POST"
        db_request.user = UserFactory.create()
        db_request.remote_addr = "10.10.10.10"
        db_request.POST = MultiDict([
            ("role_id", owner_role.id),
            ("role_id", maintainer_role.id),
            ("role_name", new_role_name),
        ])
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )

        result = views.change_project_role(project, db_request)

        assert db_request.db.query(Role).all() == [maintainer_role]
        assert db_request.route_path.calls == [
            pretend.call('manage.project.roles', project_name=project.name),
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Successfully changed role", queue="success"),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        entry = db_request.db.query(JournalEntry).one()

        assert entry.name == project.name
        assert entry.action == "remove Owner testuser"
        assert entry.submitted_by == db_request.user
        assert entry.submitted_from == db_request.remote_addr

    def test_change_missing_role(self, db_request):
        project = ProjectFactory.create(name="foobar")
        missing_role_id = str(uuid.uuid4())

        db_request.method = "POST"
        db_request.user = pretend.stub()
        db_request.POST = MultiDict({
            "role_id": missing_role_id,
            "role_name": 'Owner',
        })
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )

        result = views.change_project_role(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Could not find role", queue="error"),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_change_own_owner_role(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = RoleFactory.create(
            user=user, project=project, role_name="Owner"
        )

        db_request.method = "POST"
        db_request.user = user
        db_request.POST = MultiDict({
            "role_id": role.id,
            "role_name": "Maintainer",
        })
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )

        result = views.change_project_role(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Cannot remove yourself as Owner", queue="error"),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_change_own_owner_role_when_multiple(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        owner_role = RoleFactory.create(
            user=user, project=project, role_name="Owner"
        )
        maintainer_role = RoleFactory.create(
            user=user, project=project, role_name="Maintainer"
        )

        db_request.method = "POST"
        db_request.user = user
        db_request.POST = MultiDict([
            ("role_id", owner_role.id),
            ("role_id", maintainer_role.id),
            ("role_name", "Maintainer"),
        ])
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )

        result = views.change_project_role(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Cannot remove yourself as Owner", queue="error"),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"


class TestDeleteProjectRoles:

    def test_delete_role(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = RoleFactory.create(
            user=user, project=project, role_name="Owner"
        )

        db_request.method = "POST"
        db_request.user = UserFactory.create()
        db_request.remote_addr = "10.10.10.10"
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )

        result = views.delete_project_role(project, db_request)

        assert db_request.route_path.calls == [
            pretend.call('manage.project.roles', project_name=project.name),
        ]
        assert db_request.db.query(Role).all() == []
        assert db_request.session.flash.calls == [
            pretend.call("Successfully removed role", queue="success"),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        entry = db_request.db.query(JournalEntry).one()

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
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )

        result = views.delete_project_role(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Could not find role", queue="error"),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_delete_own_owner_role(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")
        role = RoleFactory.create(
            user=user, project=project, role_name="Owner"
        )

        db_request.method = "POST"
        db_request.user = user
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )

        result = views.delete_project_role(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Cannot remove yourself as Owner", queue="error"),
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"


class TestManageProjectHistory:

    def test_get(self, db_request):
        project = ProjectFactory.create()
        older_journal = JournalEntryFactory.create(
            name=project.name,
            submitted_date=datetime.datetime(2017, 2, 5, 17, 18, 18, 462634),
        )
        newer_journal = JournalEntryFactory.create(
            name=project.name,
            submitted_date=datetime.datetime(2018, 2, 5, 17, 18, 18, 462634),
        )

        assert views.manage_project_history(project, db_request) == {
            'project': project,
            'journals': [newer_journal, older_journal],
        }
