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

from pyramid.httpexceptions import HTTPMovedPermanently

from warehouse.legacy.api import simple

from ...common.db.accounts import UserFactory
from ...common.db.packaging import (
    ProjectFactory, ReleaseFactory, FileFactory, JournalEntryFactory,
)


class TestSimpleIndex:

    def test_no_results_no_serial(self, db_request):
        assert simple.simple_index(db_request) == {"projects": []}
        assert db_request.response.headers["X-PyPI-Last-Serial"] == 0

    def test_no_results_with_serial(self, db_request):
        user = UserFactory.create(session=db_request.db)
        je = JournalEntryFactory.create(
            session=db_request.db, submitted_by=user.username,
        )
        assert simple.simple_index(db_request) == {"projects": []}
        assert db_request.response.headers["X-PyPI-Last-Serial"] == je.id

    def test_with_results_no_serial(self, db_request):
        projects = [
            (x.name, x.normalized_name)
            for x in
            [ProjectFactory.create(session=db_request.db) for _ in range(3)]
        ]
        assert simple.simple_index(db_request) == {
            "projects": sorted(projects, key=lambda x: x[1]),
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == 0

    def test_with_results_with_serial(self, db_request):
        projects = [
            (x.name, x.normalized_name)
            for x in
            [ProjectFactory.create(session=db_request.db) for _ in range(3)]
        ]
        user = UserFactory.create(session=db_request.db)
        je = JournalEntryFactory.create(
            session=db_request.db, submitted_by=user.username,
        )

        assert simple.simple_index(db_request) == {
            "projects": sorted(projects, key=lambda x: x[1]),
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == je.id


class TestSimpleDetail:

    def test_redirects(self, pyramid_request):
        project = pretend.stub(normalized_name="foo")

        pyramid_request.matchdict["name"] = "Foo"
        pyramid_request.current_route_path = pretend.call_recorder(
            lambda name: "/foobar/"
        )

        resp = simple.simple_detail(project, pyramid_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/foobar/"
        assert pyramid_request.current_route_path.calls == [
            pretend.call(name="foo"),
        ]

    def test_no_files_no_serial(self, db_request):
        project = ProjectFactory.create(session=db_request.db)
        db_request.matchdict["name"] = project.normalized_name
        user = UserFactory.create(session=db_request.db)
        JournalEntryFactory.create(
            session=db_request.db, submitted_by=user.username,
        )

        assert simple.simple_detail(project, db_request) == {
            "project": project,
            "files": [],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == 0

    def test_no_files_with_seiral(self, db_request):
        project = ProjectFactory.create(session=db_request.db)
        db_request.matchdict["name"] = project.normalized_name
        user = UserFactory.create(session=db_request.db)
        je = JournalEntryFactory.create(
            session=db_request.db,
            name=project.name,
            submitted_by=user.username,
        )

        assert simple.simple_detail(project, db_request) == {
            "project": project,
            "files": [],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == je.id

    def test_with_files_no_serial(self, db_request):
        project = ProjectFactory.create(session=db_request.db)
        releases = [
            ReleaseFactory.create(session=db_request.db, project=project)
            for _ in range(3)
        ]
        files = [
            FileFactory.create(
                session=db_request.db,
                release=r,
                filename="{}-{}.tar.gz".format(project.name, r.version),
            )
            for r in releases
        ]
        db_request.matchdict["name"] = project.normalized_name
        user = UserFactory.create(session=db_request.db)
        JournalEntryFactory.create(
            session=db_request.db, submitted_by=user.username,
        )

        assert simple.simple_detail(project, db_request) == {
            "project": project,
            "files": files,
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == 0

    def test_with_files_with_seiral(self, db_request):
        project = ProjectFactory.create(session=db_request.db)
        releases = [
            ReleaseFactory.create(session=db_request.db, project=project)
            for _ in range(3)
        ]
        files = [
            FileFactory.create(
                session=db_request.db,
                release=r,
                filename="{}-{}.tar.gz".format(project.name, r.version),
            )
            for r in releases
        ]
        db_request.matchdict["name"] = project.normalized_name
        user = UserFactory.create(session=db_request.db)
        je = JournalEntryFactory.create(
            session=db_request.db,
            name=project.name,
            submitted_by=user.username,
        )

        assert simple.simple_detail(project, db_request) == {
            "project": project,
            "files": files,
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == je.id
