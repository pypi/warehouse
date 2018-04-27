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

from warehouse.admin.views import blacklist as views
from warehouse.packaging.models import BlacklistedProject, Project

from ....common.db.accounts import UserFactory
from ....common.db.packaging import (
    ProjectFactory,
    ReleaseFactory,
    RoleFactory,
    FileFactory,
    BlacklistedProjectFactory,
)


class TestBlacklistList:

    def test_no_query(self, db_request):
        db_request.db.query(BlacklistedProject).delete()
        blacklisted = sorted(
            [BlacklistedProjectFactory.create() for _ in range(30)],
            key=lambda b: canonicalize_name(b.name),
        )
        result = views.blacklist(db_request)

        assert result == {
            "blacklist": blacklisted[:25],
            "query": None,
        }

    def test_with_page(self, db_request):
        db_request.db.query(BlacklistedProject).delete()
        blacklisted = sorted(
            [BlacklistedProjectFactory.create() for _ in range(30)],
            key=lambda b: canonicalize_name(b.name),
        )
        db_request.GET["page"] = "2"
        result = views.blacklist(db_request)

        assert result == {
            "blacklist": blacklisted[25:],
            "query": None,
        }

    def test_with_invalid_page(self):
        request = pretend.stub(params={"page": "not an integer"})

        with pytest.raises(HTTPBadRequest):
            views.blacklist(request)

    def test_basic_query(self, db_request):
        db_request.db.query(BlacklistedProject).delete()
        blacklisted = sorted(
            [BlacklistedProjectFactory.create() for _ in range(30)],
            key=lambda b: canonicalize_name(b.name),
        )
        db_request.GET["q"] = blacklisted[0].name
        result = views.blacklist(db_request)

        assert result == {
            "blacklist": [blacklisted[0]],
            "query": blacklisted[0].name,
        }

    def test_wildcard_query(self, db_request):
        db_request.db.query(BlacklistedProject).delete()
        blacklisted = sorted(
            [BlacklistedProjectFactory.create() for _ in range(30)],
            key=lambda b: canonicalize_name(b.name),
        )
        db_request.GET["q"] = blacklisted[0].name[:-1] + "%"
        result = views.blacklist(db_request)

        assert result == {
            "blacklist": [blacklisted[0]],
            "query": blacklisted[0].name[:-1] + "%",
        }


class TestConfirmBlacklist:

    def test_no_project(self):
        request = pretend.stub(GET={})

        with pytest.raises(HTTPBadRequest):
            views.confirm_blacklist(request)

    def test_nothing_to_delete(self, db_request):
        db_request.GET["project"] = "foo"
        result = views.confirm_blacklist(db_request)

        assert result == {
            "blacklist": {
                "project": "foo",
                "comment": "",
            },
            "existing": {
                "project": None,
                "releases": [],
                "files": [],
                "roles": [],
            }
        }

    def test_stuff_to_delete(self, db_request):
        project = ProjectFactory.create()
        db_request.GET["project"] = project.name
        result = views.confirm_blacklist(db_request)

        assert result == {
            "blacklist": {
                "project": project.name,
                "comment": "",
            },
            "existing": {
                "project": project,
                "releases": [],
                "files": [],
                "roles": [],
            }
        }


class TestAddBlacklist:

    def test_no_project(self):
        request = pretend.stub(POST={})

        with pytest.raises(HTTPBadRequest):
            views.add_blacklist(request)

    def test_no_confirm(self):
        request = pretend.stub(
            POST={"project": "foo"},
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            current_route_path=lambda: "/foo/bar/",
        )

        result = views.add_blacklist(request)

        assert request.session.flash.calls == [
            pretend.call("Must confirm the blacklist request", queue="error"),
        ]
        assert result.status_code == 303
        assert result.headers["Location"] == "/foo/bar/"

    def test_wrong_confirm(self):
        request = pretend.stub(
            POST={"project": "foo", "confirm": "bar"},
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            current_route_path=lambda: "/foo/bar/",
        )

        result = views.add_blacklist(request)

        assert request.session.flash.calls == [
            pretend.call("'bar' is not the same as 'foo'", queue="error"),
        ]
        assert result.status_code == 303
        assert result.headers["Location"] == "/foo/bar/"

    def test_adds_blacklist(self, db_request):
        db_request.user = UserFactory.create()
        db_request.POST["project"] = "foo"
        db_request.POST["confirm"] = "foo"
        db_request.POST["comment"] = "This is a comment"
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )
        db_request.route_path = lambda a: "/admin/blacklist/"

        views.add_blacklist(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Successfully blacklisted 'foo'", queue="success"),
        ]

        blacklist = (
            db_request.db.query(BlacklistedProject)
                         .filter(BlacklistedProject.name == "foo")
                         .one()
        )

        assert blacklist.name == "foo"
        assert blacklist.blacklisted_by == db_request.user
        assert blacklist.comment == "This is a comment"

    def test_adds_blacklist_with_deletes(self, db_request):
        db_request.user = UserFactory.create()
        db_request.POST["project"] = "foo"
        db_request.POST["confirm"] = "foo"
        db_request.POST["comment"] = "This is a comment"
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )
        db_request.route_path = lambda a: "/admin/blacklist/"
        db_request.remote_addr = "192.168.1.1"

        project = ProjectFactory.create(name="foo")
        release = ReleaseFactory.create(project=project)
        FileFactory.create(
            name=project.name,
            version=release.version,
            filename="who cares",
        )
        RoleFactory.create(project=project, user=db_request.user)

        views.add_blacklist(db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                "Successfully deleted the project 'foo'",
                queue='success'
            ),
            pretend.call("Successfully blacklisted 'foo'", queue="success"),
        ]

        blacklist = (
            db_request.db.query(BlacklistedProject)
                         .filter(BlacklistedProject.name == "foo")
                         .one()
        )

        assert blacklist.name == "foo"
        assert blacklist.blacklisted_by == db_request.user
        assert blacklist.comment == "This is a comment"

        assert not (db_request.db.query(Project)
                                 .filter(Project.name == "foo").count())


class TestRemoveBlacklist:

    def test_no_blacklist_id(self):
        request = pretend.stub(POST={})

        with pytest.raises(HTTPBadRequest):
            views.remove_blacklist(request)

    def test_blacklist_id_not_exist(self, db_request):
        db_request.POST["blacklist_id"] = str(uuid.uuid4())

        with pytest.raises(HTTPNotFound):
            views.remove_blacklist(db_request)

    def test_deletes_blacklist(self, db_request):
        blacklist = BlacklistedProjectFactory.create()
        db_request.POST["blacklist_id"] = str(blacklist.id)
        db_request.route_path = lambda a: "/admin/blacklist/"

        resp = views.remove_blacklist(db_request)

        assert resp.status_code == 303
        assert resp.headers["Location"] == "/admin/blacklist/"
        assert not (db_request.db.query(BlacklistedProject)
                                 .filter(BlacklistedProject.id == blacklist.id)
                                 .count())

    def test_deletes_blacklist_with_redirect(self, db_request):
        blacklist = BlacklistedProjectFactory.create()
        db_request.POST["blacklist_id"] = str(blacklist.id)
        db_request.POST["next"] = "/another/url/"
        db_request.route_path = lambda a: "/admin/blacklist/"

        resp = views.remove_blacklist(db_request)

        assert resp.status_code == 303
        assert resp.headers["Location"] == "/another/url/"
        assert not (db_request.db.query(BlacklistedProject)
                                 .filter(BlacklistedProject.id == blacklist.id)
                                 .count())
