# SPDX-License-Identifier: Apache-2.0

import uuid

from collections import defaultdict

import pretend
import pytest

from packaging.utils import canonicalize_name
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther

from warehouse.admin.views import prohibited_project_names as views
from warehouse.packaging.models import ProhibitedProjectName, Project, Role

from ....common.db.accounts import UserFactory
from ....common.db.packaging import (
    FileFactory,
    ProhibitedProjectFactory,
    ProjectFactory,
    ReleaseFactory,
    RoleFactory,
)


class TestProhibitedProjectNameList:
    def test_no_query(self, db_request):
        db_request.db.query(ProhibitedProjectName).delete()
        prohibited = sorted(
            ProhibitedProjectFactory.create_batch(30),
            key=lambda b: canonicalize_name(b.name),
        )
        result = views.prohibited_project_names(db_request)

        assert result == {"prohibited_project_names": prohibited[:25], "query": None}

    def test_with_page(self, db_request):
        db_request.db.query(ProhibitedProjectName).delete()
        prohibited = sorted(
            ProhibitedProjectFactory.create_batch(30),
            key=lambda b: canonicalize_name(b.name),
        )
        db_request.GET["page"] = "2"
        result = views.prohibited_project_names(db_request)

        assert result == {"prohibited_project_names": prohibited[25:], "query": None}

    def test_with_invalid_page(self):
        request = pretend.stub(params={"page": "not an integer"})

        with pytest.raises(HTTPBadRequest):
            views.prohibited_project_names(request)

    def test_basic_query(self, db_request):
        db_request.db.query(ProhibitedProjectName).delete()
        prohibited = sorted(
            ProhibitedProjectFactory.create_batch(30),
            key=lambda b: canonicalize_name(b.name),
        )
        db_request.GET["q"] = prohibited[0].name
        result = views.prohibited_project_names(db_request)

        assert result == {
            "prohibited_project_names": [prohibited[0]],
            "query": prohibited[0].name,
        }

    def test_wildcard_query(self, db_request):
        db_request.db.query(ProhibitedProjectName).delete()
        prohibited = sorted(
            ProhibitedProjectFactory.create_batch(30),
            key=lambda b: canonicalize_name(b.name),
        )
        db_request.GET["q"] = prohibited[0].name[:-1] + "%"
        result = views.prohibited_project_names(db_request)

        assert result == {
            "prohibited_project_names": [prohibited[0]],
            "query": prohibited[0].name[:-1] + "%",
        }


class TestConfirmProhibitedProjectName:
    def test_no_project(self):
        request = pretend.stub(GET={})

        with pytest.raises(HTTPBadRequest):
            views.confirm_prohibited_project_names(request)

    def test_nothing_to_delete(self, db_request):
        db_request.GET["project"] = "foo"
        result = views.confirm_prohibited_project_names(db_request)

        assert result == {
            "prohibited_project_names": {"project": "foo", "comment": ""},
            "existing": {
                "project": None,
                "releases": [],
                "files": [],
                "roles": [],
                "releases_by_date": defaultdict(list),
            },
        }

    def test_stuff_to_delete(self, db_request):
        db_request.user = UserFactory.create()
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project)
        file_ = FileFactory.create(release=release, filename="who cares")
        role = RoleFactory.create(project=project, user=db_request.user)

        db_request.GET["project"] = project.name
        result = views.confirm_prohibited_project_names(db_request)

        assert result == {
            "prohibited_project_names": {"project": project.name, "comment": ""},
            "existing": {
                "project": project,
                "releases": [release],
                "files": [file_],
                "roles": [role],
                "releases_by_date": defaultdict(
                    list, {release.created.strftime("%Y-%m-%d"): [release]}
                ),
            },
        }


class TestAddProhibitedProjectName:
    def test_no_project(self):
        request = pretend.stub(POST={})

        with pytest.raises(HTTPBadRequest):
            views.add_prohibited_project_names(request)

    def test_no_confirm(self):
        request = pretend.stub(
            POST={"project": "foo"},
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            current_route_path=lambda: "/foo/bar/",
        )

        result = views.add_prohibited_project_names(request)

        assert request.session.flash.calls == [
            pretend.call("Confirm the prohibited project name request", queue="error")
        ]
        assert result.status_code == 303
        assert result.headers["Location"] == "/foo/bar/"

    def test_wrong_confirm(self):
        request = pretend.stub(
            POST={"project": "foo", "confirm": "bar"},
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            current_route_path=lambda: "/foo/bar/",
        )

        result = views.add_prohibited_project_names(request)

        assert request.session.flash.calls == [
            pretend.call("'bar' is not the same as 'foo'", queue="error")
        ]
        assert result.status_code == 303
        assert result.headers["Location"] == "/foo/bar/"

    @pytest.mark.parametrize(
        ("project_name", "prohibit_name"),
        [
            ("foobar", "foobar"),
            ("FoObAr", "fOoBaR"),
        ],
    )
    def test_already_existing_prohibited_project_names(
        self, db_request, project_name, prohibit_name
    ):
        ProhibitedProjectFactory.create(name=project_name)

        db_request.db.expire_all()
        db_request.user = UserFactory.create()
        db_request.POST["project"] = prohibit_name
        db_request.POST["confirm"] = prohibit_name
        db_request.POST["comment"] = "This is a comment"
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = lambda a: "/admin/prohibited_project_names/"

        result = views.add_prohibited_project_names(db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                f"{prohibit_name!r} has already been prohibited.",
                queue="error",
            )
        ]
        assert result.status_code == 303
        assert result.headers["Location"] == "/admin/prohibited_project_names/"

    def test_adds_prohibited_project_name(self, db_request):
        db_request.user = UserFactory.create()
        db_request.POST["project"] = "foo"
        db_request.POST["confirm"] = "foo"
        db_request.POST["comment"] = "This is a comment"
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = lambda a: "/admin/prohibited_project_names/"

        views.add_prohibited_project_names(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Prohibited Project Name 'foo'", queue="success")
        ]

        prohibited_project_name = (
            db_request.db.query(ProhibitedProjectName)
            .filter(ProhibitedProjectName.name == "foo")
            .one()
        )

        assert prohibited_project_name.name == "foo"
        assert prohibited_project_name.prohibited_by == db_request.user
        assert prohibited_project_name.comment == "This is a comment"

    def test_adds_prohibited_project_name_with_deletes(self, db_request):
        db_request.user = UserFactory.create()
        db_request.POST["project"] = "foo"
        db_request.POST["confirm"] = "foo"
        db_request.POST["comment"] = "This is a comment"
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = lambda a: "/admin/prohibited_project_names/"

        project = ProjectFactory.create(name="foo")
        release = ReleaseFactory.create(project=project)
        FileFactory.create(release=release, filename="who cares")
        RoleFactory.create(project=project, user=db_request.user)

        views.add_prohibited_project_names(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Deleted the project 'foo'", queue="success"),
            pretend.call("Prohibited Project Name 'foo'", queue="success"),
        ]

        prohibited_project_name = (
            db_request.db.query(ProhibitedProjectName)
            .filter(ProhibitedProjectName.name == "foo")
            .one()
        )

        assert prohibited_project_name.name == "foo"
        assert prohibited_project_name.prohibited_by == db_request.user
        assert prohibited_project_name.comment == "This is a comment"

        assert not (db_request.db.query(Project).filter(Project.name == "foo").count())


class TestBulkAddProhibitedProjectName:
    def test_get(self):
        request = pretend.stub(method="GET")

        assert views.bulk_add_prohibited_project_names(request) == {}

    def test_bulk_add(self, db_request):
        db_request.user = UserFactory.create()
        db_request.method = "POST"
        comment = "This is a comment"

        already_existing_prohibition = ProhibitedProjectFactory.create(
            name="prohibition-already-exists",
            prohibited_by=db_request.user,
            comment=comment,
        )

        already_existing_project = ProjectFactory.create(name="project-already-exists")
        release = ReleaseFactory.create(project=already_existing_project)
        FileFactory.create(release=release, filename="who cares")
        RoleFactory.create(project=already_existing_project, user=db_request.user)

        project_names = [
            already_existing_prohibition.name,
            already_existing_project.name,
            "doesnt-already-exist",
        ]

        db_request.POST["projects"] = "\n".join(project_names)
        db_request.POST["comment"] = comment

        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = lambda a: "/admin/prohibited_project_names/bulk"

        result = views.bulk_add_prohibited_project_names(db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                f"Prohibited {len(project_names)!r} projects",
                queue="success",
            )
        ]
        assert result.status_code == 303
        assert result.headers["Location"] == "/admin/prohibited_project_names/bulk"

        for project_name in project_names:
            prohibition = (
                db_request.db.query(ProhibitedProjectName)
                .filter(ProhibitedProjectName.name == project_name)
                .one()
            )

            assert prohibition.name == project_name
            assert prohibition.prohibited_by == db_request.user
            assert prohibition.comment == comment

            assert (
                db_request.db.query(Project)
                .filter(Project.name == project_name)
                .count()
                == 0
            )

    def test_adds_prohibited_project_name(self, db_request):
        db_request.user = UserFactory.create()
        db_request.POST["project"] = "foo"
        db_request.POST["confirm"] = "foo"
        db_request.POST["comment"] = "This is a comment"
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = lambda a: "/admin/prohibited_project_names/"

        views.add_prohibited_project_names(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Prohibited Project Name 'foo'", queue="success")
        ]

        prohibited_project_name = (
            db_request.db.query(ProhibitedProjectName)
            .filter(ProhibitedProjectName.name == "foo")
            .one()
        )

        assert prohibited_project_name.name == "foo"
        assert prohibited_project_name.prohibited_by == db_request.user
        assert prohibited_project_name.comment == "This is a comment"

    def test_adds_prohibited_project_name_with_deletes(self, db_request):
        db_request.user = UserFactory.create()
        db_request.POST["project"] = "foo"
        db_request.POST["confirm"] = "foo"
        db_request.POST["comment"] = "This is a comment"
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = lambda a: "/admin/prohibited_project_names/"

        project = ProjectFactory.create(name="foo")
        release = ReleaseFactory.create(project=project)
        FileFactory.create(release=release, filename="who cares")
        RoleFactory.create(project=project, user=db_request.user)

        views.add_prohibited_project_names(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Deleted the project 'foo'", queue="success"),
            pretend.call("Prohibited Project Name 'foo'", queue="success"),
        ]

        prohibited_project_name = (
            db_request.db.query(ProhibitedProjectName)
            .filter(ProhibitedProjectName.name == "foo")
            .one()
        )

        assert prohibited_project_name.name == "foo"
        assert prohibited_project_name.prohibited_by == db_request.user
        assert prohibited_project_name.comment == "This is a comment"

        assert not (db_request.db.query(Project).filter(Project.name == "foo").count())


class TestRemoveProhibitedProjectName:
    def test_no_prohibited_project_name_id(self):
        request = pretend.stub(POST={})

        with pytest.raises(HTTPBadRequest):
            views.remove_prohibited_project_names(request)

    def test_prohibited_project_name_id_not_exist(self, db_request):
        db_request.POST["prohibited_project_name_id"] = str(uuid.uuid4())

        with pytest.raises(HTTPNotFound):
            views.remove_prohibited_project_names(db_request)

    def test_deletes_prohibited_project_name(self, db_request):
        prohibited_project_name = ProhibitedProjectFactory.create()
        db_request.POST["prohibited_project_name_id"] = str(prohibited_project_name.id)
        db_request.route_path = lambda a: "/admin/prohibited_project_names/"

        resp = views.remove_prohibited_project_names(db_request)

        assert resp.status_code == 303
        assert resp.headers["Location"] == "/admin/prohibited_project_names/"
        assert not (
            db_request.db.query(ProhibitedProjectName)
            .filter(ProhibitedProjectName.id == prohibited_project_name.id)
            .count()
        )

    def test_deletes_prohibited_project_name_with_redirect(self, db_request):
        prohibited_project_name = ProhibitedProjectFactory.create()
        db_request.POST["prohibited_project_name_id"] = str(prohibited_project_name.id)
        db_request.POST["next"] = "/another/url/"
        db_request.route_path = lambda a: "/admin/prohibited_project_names/"

        resp = views.remove_prohibited_project_names(db_request)

        assert resp.status_code == 303
        assert resp.headers["Location"] == "/another/url/"
        assert not (
            db_request.db.query(ProhibitedProjectName)
            .filter(ProhibitedProjectName.id == prohibited_project_name.id)
            .count()
        )


class TestReleaseProhibitedProjectName:
    def test_no_prohibited_project_name(self, db_request):
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.current_route_path = lambda: "/admin/prohibited_project_names/"

        result = views.release_prohibited_project_name(db_request)
        assert isinstance(result, HTTPSeeOther)
        assert db_request.session.flash.calls == [
            pretend.call("Provide a project name", queue="error")
        ]

    def test_prohibited_project_name_does_not_exist(self, db_request):
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.current_route_path = lambda: "/admin/prohibited_project_names/"

        db_request.POST["project_name"] = "wu"

        result = views.release_prohibited_project_name(db_request)
        assert isinstance(result, HTTPSeeOther)
        assert db_request.session.flash.calls == [
            pretend.call(
                "'wu' does not exist on prohibited project name list.", queue="error"
            )
        ]

    def test_project_exists(self, db_request):
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.current_route_path = lambda: "/admin/prohibited_project_names/"

        ProhibitedProjectFactory.create(name="tang")
        ProjectFactory.create(name="tang")

        db_request.POST["project_name"] = "tang"
        db_request.POST["username"] = "rza"

        result = views.release_prohibited_project_name(db_request)
        assert isinstance(result, HTTPSeeOther)
        assert db_request.session.flash.calls == [
            pretend.call(
                "'tang' exists and is not on the prohibited project name list.",
                queue="error",
            )
        ]

    def test_no_username(self, db_request):
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.current_route_path = lambda: "/admin/prohibited_project_names/"

        ProhibitedProjectFactory.create(name="wutang")

        db_request.POST["project_name"] = "wutang"

        result = views.release_prohibited_project_name(db_request)
        assert isinstance(result, HTTPSeeOther)
        assert db_request.session.flash.calls == [
            pretend.call("Provide a username", queue="error")
        ]

    def test_user_does_not_exist(self, db_request):
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.current_route_path = lambda: "/admin/prohibited_project_names/"

        ProhibitedProjectFactory.create(name="wutang")

        db_request.POST["project_name"] = "wutang"
        db_request.POST["username"] = "methodman"

        result = views.release_prohibited_project_name(db_request)
        assert isinstance(result, HTTPSeeOther)
        assert db_request.session.flash.calls == [
            pretend.call("Unknown username 'methodman'", queue="error")
        ]

    def test_creates_project_and_assigns_role(self, db_request):
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = (
            lambda *a, **kw: f"/admin/projects/{kw['project_name']}/"
        )

        user = UserFactory.create(username="methodman")
        ProhibitedProjectFactory.create(name="wutangclan")

        db_request.POST["project_name"] = "wutangclan"
        db_request.POST["username"] = "methodman"

        result = views.release_prohibited_project_name(db_request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/admin/projects/wutangclan/"
        assert db_request.session.flash.calls == [
            pretend.call("'wutangclan' released to 'methodman'.", queue="success")
        ]

        assert not (
            db_request.db.query(ProhibitedProjectName)
            .filter(ProhibitedProjectName.name == "wutangclan")
            .count()
        )
        project = (
            db_request.db.query(Project).filter(Project.name == "wutangclan").one()
        )
        assert project is not None
        role = (
            db_request.db.query(Role)
            .filter(
                Role.user == user, Role.project == project, Role.role_name == "Owner"
            )
            .first()
        )
        assert role is not None
        all_roles = db_request.db.query(Role).filter(Role.project == project).count()
        assert all_roles == 1
