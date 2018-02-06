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

import uuid

import pretend
import pytest

from pyramid.httpexceptions import HTTPSeeOther
from webob.multidict import MultiDict

from warehouse.manage import views
from warehouse.accounts.interfaces import IUserService
from warehouse.packaging.models import JournalEntry, Project, Role

from ...common.db.packaging import ProjectFactory, RoleFactory, UserFactory


class TestManageProfile:

    def test_manage_profile(self, monkeypatch):
        user_service = pretend.stub()
        name = pretend.stub()
        request = pretend.stub(
            find_service=lambda *a, **kw: user_service,
            user=pretend.stub(name=name),
        )
        save_profile_obj = pretend.stub()
        save_profile_cls = pretend.call_recorder(lambda **kw: save_profile_obj)
        monkeypatch.setattr(views, 'SaveProfileForm', save_profile_cls)
        view_class = views.ManageProfileViews(request)

        assert view_class.manage_profile() == {
            'save_profile_form': save_profile_obj,
        }
        assert view_class.request == request
        assert view_class.user_service == user_service
        assert save_profile_cls.calls == [
            pretend.call(name=name),
        ]

    def test_save_profile(self, monkeypatch):
        update_user = pretend.call_recorder(lambda *a, **kw: None)
        request = pretend.stub(
            POST={'name': 'new name'},
            user=pretend.stub(id=pretend.stub()),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            find_service=pretend.call_recorder(
                lambda iface, context: pretend.stub(update_user=update_user)
            ),
        )
        save_profile_obj = pretend.stub(
            validate=lambda: True,
            data=request.POST,
        )
        save_profile_cls = pretend.call_recorder(lambda d: save_profile_obj)
        monkeypatch.setattr(views, 'SaveProfileForm', save_profile_cls)
        view_class = views.ManageProfileViews(request)

        assert view_class.save_profile() == {
            'save_profile_form': save_profile_obj,
        }
        assert request.session.flash.calls == [
            pretend.call('Public profile updated.', queue='success'),
        ]
        assert update_user.calls == [
            pretend.call(request.user.id, **request.POST)
        ]
        assert save_profile_cls.calls == [
            pretend.call(request.POST),
        ]

    def test_save_profile_validation_fails(self, monkeypatch):
        update_user = pretend.call_recorder(lambda *a, **kw: None)
        request = pretend.stub(
            POST={'name': 'new name'},
            user=pretend.stub(id=pretend.stub()),
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            find_service=pretend.call_recorder(
                lambda iface, context: pretend.stub(update_user=update_user)
            ),
        )
        save_profile_obj = pretend.stub(validate=lambda: False)
        save_profile_cls = pretend.call_recorder(lambda d: save_profile_obj)
        monkeypatch.setattr(views, 'SaveProfileForm', save_profile_cls)
        view_class = views.ManageProfileViews(request)

        assert view_class.save_profile() == {
            'save_profile_form': save_profile_obj,
        }
        assert request.session.flash.calls == []
        assert update_user.calls == []
        assert save_profile_cls.calls == [
            pretend.call(request.POST),
        ]


class TestManageProjects:

    def test_manage_projects(self):
        request = pretend.stub()

        assert views.manage_projects(request) == {}


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
            pretend.call("Must confirm the request.", queue="error"),
        ]

    def test_delete_project_wrong_confirm(self):
        project = pretend.stub(normalized_name='foo')
        request = pretend.stub(
            POST={"confirm": "bar"},
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
        db_request.POST["confirm"] = project.normalized_name
        db_request.user = UserFactory.create()
        db_request.remote_addr = "192.168.1.1"

        result = views.delete_project(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                "Successfully deleted the project 'foo'.",
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
                action="remove",
                version=release.version,
                submitted_by=request.user,
                submitted_from=request.remote_addr,
            ),
        ]
        assert request.session.flash.calls == [
            pretend.call(
                f"Successfully deleted release {release.version!r}.",
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
                "Must confirm the request.", queue='error'
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
                'confirm_filename': release_file.filename,
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
                f"Successfully deleted file {release_file.filename!r}.",
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
            POST={'confirm_filename': ''},
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
                "Must confirm the request.", queue='error'
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
            POST={'confirm_filename': 'invalid'},
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
                f"'invalid' is not the same as {release_file.filename!r}",
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

    def test_post_new_role(self, db_request):
        project = ProjectFactory.create(name="foobar")
        user = UserFactory.create(username="testuser")

        user_service = pretend.stub(
            find_userid=lambda username: user.id,
            get_user=lambda userid: user,
        )
        db_request.find_service = pretend.call_recorder(
            lambda iface, context: user_service
        )
        db_request.method = "POST"
        db_request.POST = pretend.stub()
        db_request.remote_addr = "10.10.10.10"
        db_request.user = UserFactory.create()
        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data=user.username),
            role_name=pretend.stub(data="Owner"),
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
            pretend.call("Added collaborator 'testuser'", queue="success"),
        ]

        # Only one role is created
        role = db_request.db.query(Role).one()

        assert result == {
            "project": project,
            "roles_by_user": {user.username: [role]},
            "form": form_obj,
        }

        entry = db_request.db.query(JournalEntry).one()

        assert entry.name == project.name
        assert entry.action == "add Owner testuser"
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
