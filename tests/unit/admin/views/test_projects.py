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

import pretend
import pytest

from pyramid.httpexceptions import (
    HTTPBadRequest, HTTPMovedPermanently, HTTPSeeOther,
)

from warehouse.admin.views import projects as views
from warehouse.packaging.models import Project

from ....common.db.accounts import UserFactory
from ....common.db.packaging import (
    JournalEntryFactory,
    ProjectFactory,
    ReleaseFactory,
    RoleFactory,
)


class TestProjectList:

    def test_no_query(self, db_request):
        projects = sorted(
            [ProjectFactory.create() for _ in range(30)],
            key=lambda p: p.normalized_name,
        )
        result = views.project_list(db_request)

        assert result == {
            "projects": projects[:25],
            "query": None,
        }

    def test_with_page(self, db_request):
        projects = sorted(
            [ProjectFactory.create() for _ in range(30)],
            key=lambda p: p.normalized_name,
        )
        db_request.GET["page"] = "2"
        result = views.project_list(db_request)

        assert result == {
            "projects": projects[25:],
            "query": None,
        }

    def test_with_invalid_page(self):
        request = pretend.stub(params={"page": "not an integer"})

        with pytest.raises(HTTPBadRequest):
            views.project_list(request)

    def test_basic_query(self, db_request):
        projects = sorted(
            [ProjectFactory.create() for _ in range(5)],
            key=lambda p: p.normalized_name,
        )
        db_request.GET["q"] = projects[0].name
        result = views.project_list(db_request)

        assert result == {
            "projects": [projects[0]],
            "query": projects[0].name,
        }

    def test_wildcard_query(self, db_request):
        projects = sorted(
            [ProjectFactory.create() for _ in range(5)],
            key=lambda p: p.normalized_name,
        )
        db_request.GET["q"] = projects[0].name[:-1] + "%"
        result = views.project_list(db_request)

        assert result == {
            "projects": [projects[0]],
            "query": projects[0].name[:-1] + "%",
        }


class TestProjectDetail:

    def test_gets_project(self, db_request):
        project = ProjectFactory.create()
        journals = sorted(
            [JournalEntryFactory(name=project.name)
             for _ in range(75)],
            key=lambda x: (x.submitted_date, x.id),
            reverse=True,
        )
        roles = sorted(
            [RoleFactory(project=project) for _ in range(5)],
            key=lambda x: (x.role_name, x.user.username),
        )
        db_request.matchdict["project_name"] = str(project.normalized_name)
        result = views.project_detail(project, db_request)

        assert result["project"] == project
        assert result["maintainers"] == roles
        assert result["journal"] == journals[:30]

    def test_non_normalized_name(self, db_request):
        project = ProjectFactory.create()
        db_request.matchdict["project_name"] = str(project.name)
        db_request.current_route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/projects/the-redirect/"
        )
        with pytest.raises(HTTPMovedPermanently):
            views.project_detail(project, db_request)


class TestReleaseDetail:

    def test_gets_release(self):
        release = pretend.stub()
        request = pretend.stub()

        assert views.release_detail(release, request) == {
            'release': release,
        }


class TestProjectReleasesList:

    def test_no_query(self, db_request):
        project = ProjectFactory.create()
        releases = sorted(
            [
                ReleaseFactory.create(project=project)
                for _ in range(30)
            ],
            key=lambda x: x._pypi_ordering,
            reverse=True,
        )
        db_request.matchdict["project_name"] = project.normalized_name
        result = views.releases_list(project, db_request)

        assert result == {
            "releases": releases[:25],
            "project": project,
            "query": None,
        }

    def test_with_page(self, db_request):
        project = ProjectFactory.create()
        releases = sorted(
            [
                ReleaseFactory.create(project=project)
                for _ in range(30)
            ],
            key=lambda x: x._pypi_ordering,
            reverse=True,
        )
        db_request.matchdict["project_name"] = project.normalized_name
        db_request.GET["page"] = "2"
        result = views.releases_list(project, db_request)

        assert result == {
            "releases": releases[25:],
            "project": project,
            "query": None,
        }

    def test_with_invalid_page(self, db_request):
        project = ProjectFactory.create()
        db_request.matchdict["project_name"] = project.normalized_name
        db_request.GET["page"] = "not an integer"

        with pytest.raises(HTTPBadRequest):
            views.releases_list(project, db_request)

    def test_version_query(self, db_request):
        project = ProjectFactory.create()
        releases = sorted(
            [
                ReleaseFactory.create(project=project)
                for _ in range(30)
            ],
            key=lambda x: x._pypi_ordering,
            reverse=True,
        )
        db_request.matchdict["project_name"] = project.normalized_name
        db_request.GET["q"] = "version:{}".format(releases[3].version)
        result = views.releases_list(project, db_request)

        assert result == {
            "releases": [releases[3]],
            "project": project,
            "query": "version:{}".format(releases[3].version),
        }

    def test_invalid_key_query(self, db_request):
        project = ProjectFactory.create()
        releases = sorted(
            [
                ReleaseFactory.create(project=project)
                for _ in range(30)
            ],
            key=lambda x: x._pypi_ordering,
            reverse=True,
        )
        db_request.matchdict["project_name"] = project.normalized_name
        db_request.GET["q"] = "user:{}".format(releases[3].uploader)
        result = views.releases_list(project, db_request)

        assert result == {
            "releases": releases[:25],
            "project": project,
            "query": "user:{}".format(releases[3].uploader),
        }

    def test_basic_query(self, db_request):
        project = ProjectFactory.create()
        releases = sorted(
            [
                ReleaseFactory.create(project=project)
                for _ in range(30)
            ],
            key=lambda x: x._pypi_ordering,
            reverse=True,
        )
        db_request.matchdict["project_name"] = project.normalized_name
        db_request.GET["q"] = "{}".format(releases[3].version)
        result = views.releases_list(project, db_request)

        assert result == {
            "releases": releases[:25],
            "project": project,
            "query": "{}".format(releases[3].version),
        }

    def test_non_normalized_name(self, db_request):
        project = ProjectFactory.create()
        db_request.matchdict["project_name"] = str(project.name)
        db_request.current_route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/projects/the-redirect/releases/"
        )
        with pytest.raises(HTTPMovedPermanently):
            views.releases_list(project, db_request)


class TestProjectJournalsList:

    def test_no_query(self, db_request):
        project = ProjectFactory.create()
        journals = sorted(
            [JournalEntryFactory(name=project.name)
             for _ in range(30)],
            key=lambda x: (x.submitted_date, x.id),
            reverse=True,
        )
        db_request.matchdict["project_name"] = project.normalized_name
        result = views.journals_list(project, db_request)

        assert result == {
            "journals": journals[:25],
            "project": project,
            "query": None,
        }

    def test_with_page(self, db_request):
        project = ProjectFactory.create()
        journals = sorted(
            [JournalEntryFactory(name=project.name)
             for _ in range(30)],
            key=lambda x: (x.submitted_date, x.id),
            reverse=True,
        )
        db_request.matchdict["project_name"] = project.normalized_name
        db_request.GET["page"] = "2"
        result = views.journals_list(project, db_request)

        assert result == {
            "journals": journals[25:],
            "project": project,
            "query": None,
        }

    def test_with_invalid_page(self, db_request):
        project = ProjectFactory.create()
        db_request.matchdict["project_name"] = project.normalized_name
        db_request.GET["page"] = "not an integer"

        with pytest.raises(HTTPBadRequest):
            views.journals_list(project, db_request)

    def test_version_query(self, db_request):
        project = ProjectFactory.create()
        journals = sorted(
            [JournalEntryFactory(name=project.name)
             for _ in range(30)],
            key=lambda x: (x.submitted_date, x.id),
            reverse=True,
        )
        db_request.matchdict["project_name"] = project.normalized_name
        db_request.GET["q"] = "version:{}".format(journals[3].version)
        result = views.journals_list(project, db_request)

        assert result == {
            "journals": [journals[3]],
            "project": project,
            "query": "version:{}".format(journals[3].version),
        }

    def test_invalid_key_query(self, db_request):
        project = ProjectFactory.create()
        journals = sorted(
            [JournalEntryFactory(name=project.name)
             for _ in range(30)],
            key=lambda x: (x.submitted_date, x.id),
            reverse=True,
        )
        db_request.matchdict["project_name"] = project.normalized_name
        db_request.GET["q"] = "user:{}".format(journals[3].submitted_by)
        result = views.journals_list(project, db_request)

        assert result == {
            "journals": journals[:25],
            "project": project,
            "query": "user:{}".format(journals[3].submitted_by),
        }

    def test_basic_query(self, db_request):
        project = ProjectFactory.create()
        journals = sorted(
            [JournalEntryFactory(name=project.name)
             for _ in range(30)],
            key=lambda x: (x.submitted_date, x.id),
            reverse=True,
        )
        db_request.matchdict["project_name"] = project.normalized_name
        db_request.GET["q"] = "{}".format(journals[3].version)
        result = views.journals_list(project, db_request)

        assert result == {
            "journals": journals[:25],
            "project": project,
            "query": "{}".format(journals[3].version),
        }

    def test_non_normalized_name(self, db_request):
        project = ProjectFactory.create()
        db_request.matchdict["project_name"] = str(project.name)
        db_request.current_route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/projects/the-redirect/journals/"
        )
        with pytest.raises(HTTPMovedPermanently):
            views.journals_list(project, db_request)


class TestProjectSetLimit:
    def test_sets_limitwith_integer(self, db_request):
        project = ProjectFactory.create(name="foo")

        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/projects/")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )
        db_request.matchdict["project_name"] = project.normalized_name
        db_request.POST["upload_limit"] = "90"

        views.set_upload_limit(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                "Successfully set the upload limit on 'foo'",
                queue="success"),
        ]

        assert project.upload_limit == 90 * views.ONE_MB

    def test_sets_limit_with_none(self, db_request):
        project = ProjectFactory.create(name="foo")
        project.upload_limit = 90 * views.ONE_MB

        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/projects/")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )
        db_request.matchdict["project_name"] = project.normalized_name

        views.set_upload_limit(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                "Successfully set the upload limit on 'foo'",
                queue="success"),
        ]

        assert project.upload_limit is None

    def test_sets_limit_with_non_integer(self, db_request):
        project = ProjectFactory.create(name="foo")

        db_request.matchdict["project_name"] = project.normalized_name
        db_request.POST["upload_limit"] = "meep"

        with pytest.raises(HTTPBadRequest):
            views.set_upload_limit(project, db_request)

    def test_sets_limit_with_less_than_minimum(self, db_request):
        project = ProjectFactory.create(name="foo")

        db_request.matchdict["project_name"] = project.normalized_name
        db_request.POST["upload_limit"] = "20"

        with pytest.raises(HTTPBadRequest):
            views.set_upload_limit(project, db_request)


class TestDeleteProject:

    def test_no_confirm(self):
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

    def test_wrong_confirm(self):
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

    def test_deletes_project(self, db_request):
        project = ProjectFactory.create(name="foo")

        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/projects/")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None),
        )
        db_request.POST["confirm_project_name"] = project.normalized_name
        db_request.user = UserFactory.create()
        db_request.remote_addr = "192.168.1.1"

        views.delete_project(project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                "Successfully deleted the project 'foo'",
                queue="success"),
        ]

        assert not (db_request.db.query(Project)
                                 .filter(Project.name == "foo").count())
