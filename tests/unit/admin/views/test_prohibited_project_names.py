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

from packaging.utils import canonicalize_name
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound

from warehouse.admin.views import prohibited_project_names as views
from warehouse.packaging.models import ProhibitedProjectName, Project

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
            [ProhibitedProjectFactory.create() for _ in range(30)],
            key=lambda b: canonicalize_name(b.name),
        )
        result = views.prohibited_project_names(db_request)

        assert result == {"prohibited_project_names": prohibited[:25], "query": None}

    def test_with_page(self, db_request):
        db_request.db.query(ProhibitedProjectName).delete()
        prohibited = sorted(
            [ProhibitedProjectFactory.create() for _ in range(30)],
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
            [ProhibitedProjectFactory.create() for _ in range(30)],
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
            [ProhibitedProjectFactory.create() for _ in range(30)],
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
            "existing": {"project": None, "releases": [], "files": [], "roles": []},
        }

    def test_stuff_to_delete(self, db_request):
        project = ProjectFactory.create()
        db_request.GET["project"] = project.name
        result = views.confirm_prohibited_project_names(db_request)

        assert result == {
            "prohibited_project_names": {"project": project.name, "comment": ""},
            "existing": {"project": project, "releases": [], "files": [], "roles": []},
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

    def test_already_existing_prohibited_project_names(self, db_request):
        prohibited_project_name = ProhibitedProjectFactory.create()

        db_request.db.expire_all()
        db_request.user = UserFactory.create()
        db_request.POST["project"] = prohibited_project_name.name
        db_request.POST["confirm"] = prohibited_project_name.name
        db_request.POST["comment"] = "This is a comment"
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = lambda a: "/admin/prohibited_project_names/"

        result = views.add_prohibited_project_names(db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                f"{prohibited_project_name.name!r} has already been prohibited.",
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
        db_request.remote_addr = "192.168.1.1"

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

        resp = views.remove_prohibited_project_name(db_request)

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
