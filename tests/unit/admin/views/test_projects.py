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
import uuid

from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound
from webob.multidict import MultiDict

from warehouse.admin.views import projects as views

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

    def test_404s_on_non_existent_project(self, db_request):
        project = ProjectFactory.create()
        project_name = uuid.uuid4()
        while project_name == project.normalized_name:
            project_name = uuid.uuid4()
        db_request.matchdict["project_name"] = str(project_name)

        with pytest.raises(HTTPNotFound):
            views.project_detail(db_request)

    def test_gets_project(self, db_request):
        project = ProjectFactory.create()
        journals = sorted(
            [JournalEntryFactory(name=project.normalized_name)
             for _ in range(75)],
            key=lambda x: x.submitted_date,
            reverse=True,
        )
        roles = sorted(
            [RoleFactory(project=project) for _ in range(5)],
            key=lambda x: (x.role_name, x.user.username),
        )
        db_request.matchdict["project_name"] = str(project.normalized_name)
        db_request.POST = MultiDict(db_request.POST)
        result = views.project_detail(db_request)

        assert result["project"] == project
        assert result["maintainers"] == roles
        assert result["journal"] == journals[:50]


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
        db_request.matchdict["project_name"] = project.name
        result = views.releases_list(db_request)

        assert result == {
            "releases": releases[:25],
            "project_name": project.name,
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
        db_request.matchdict["project_name"] = project.name
        db_request.GET["page"] = "2"
        result = views.releases_list(db_request)

        assert result == {
            "releases": releases[25:],
            "project_name": project.name,
            "query": None,
        }

    def test_with_invalid_page(self):
        request = pretend.stub(
            matchdict={"project_name": "foobar"},
            params={"page": "not an integer"},
        )

        with pytest.raises(HTTPBadRequest):
            views.releases_list(request)

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
        db_request.matchdict["project_name"] = project.name
        db_request.GET["q"] = "version:{}".format(releases[3].version)
        result = views.releases_list(db_request)

        assert result == {
            "releases": [releases[3]],
            "project_name": project.name,
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
        db_request.matchdict["project_name"] = project.name
        db_request.GET["q"] = "user:{}".format(releases[3].uploader)
        result = views.releases_list(db_request)

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
        db_request.matchdict["project_name"] = project.name
        db_request.GET["q"] = "{}".format(releases[3].version)
        result = views.releases_list(db_request)

        assert result == {
            "releases": releases[:25],
            "project": project,
            "query": "{}".format(releases[3].version),
        }


class TestProjectJournalsList:

    def test_no_query(self, db_request):
        project = ProjectFactory.create()
        journals = sorted(
            [JournalEntryFactory(name=project.normalized_name)
             for _ in range(30)],
            key=lambda x: x.submitted_date,
            reverse=True,
        )
        db_request.matchdict["project_name"] = project.name
        result = views.journals_list(db_request)

        assert result == {
            "journals": journals[:25],
            "project_name": project.name,
            "query": None,
        }

    def test_with_page(self, db_request):
        project = ProjectFactory.create()
        journals = sorted(
            [JournalEntryFactory(name=project.normalized_name)
             for _ in range(30)],
            key=lambda x: x.submitted_date,
            reverse=True,
        )
        db_request.matchdict["project_name"] = project.name
        db_request.GET["page"] = "2"
        result = views.journals_list(db_request)

        assert result == {
            "journals": journals[25:],
            "project_name": project.name,
            "query": None,
        }

    def test_with_invalid_page(self):
        request = pretend.stub(
            matchdict={"project_name": "foobar"},
            params={"page": "not an integer"},
        )

        with pytest.raises(HTTPBadRequest):
            views.journals_list(request)

    def test_version_query(self, db_request):
        project = ProjectFactory.create()
        journals = sorted(
            [JournalEntryFactory(name=project.normalized_name)
             for _ in range(30)],
            key=lambda x: x.submitted_date,
            reverse=True,
        )
        db_request.matchdict["project_name"] = project.name
        db_request.GET["q"] = "version:{}".format(journals[3].version)
        result = views.journals_list(db_request)

        assert result == {
            "journals": [journals[3]],
            "project_name": project.name,
            "query": "version:{}".format(journals[3].version),
        }

    def test_invalid_key_query(self, db_request):
        project = ProjectFactory.create()
        journals = sorted(
            [JournalEntryFactory(name=project.normalized_name)
             for _ in range(30)],
            key=lambda x: x.submitted_date,
            reverse=True,
        )
        db_request.matchdict["project_name"] = project.name
        db_request.GET["q"] = "user:{}".format(journals[3].submitted_by)
        result = views.journals_list(db_request)

        assert result == {
            "journals": journals[:25],
            "project": project,
            "query": "user:{}".format(journals[3].submitted_by),
        }

    def test_basic_query(self, db_request):
        project = ProjectFactory.create()
        journals = sorted(
            [JournalEntryFactory(name=project.normalized_name)
             for _ in range(30)],
            key=lambda x: x.submitted_date,
            reverse=True,
        )
        db_request.matchdict["project_name"] = project.name
        db_request.GET["q"] = "{}".format(journals[3].version)
        result = views.journals_list(db_request)

        assert result == {
            "journals": journals[:25],
            "project": project,
            "query": "{}".format(journals[3].version),
        }
