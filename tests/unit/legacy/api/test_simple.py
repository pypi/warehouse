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

from ....common.db.accounts import UserFactory
from ....common.db.packaging import (
    FileFactory,
    JournalEntryFactory,
    ProjectFactory,
    ReleaseFactory,
)


class TestSimpleIndex:
    def test_no_results_no_serial(self, db_request):
        assert simple.simple_index(db_request) == {"projects": []}
        assert db_request.response.headers["X-PyPI-Last-Serial"] == "0"

    def test_no_results_with_serial(self, db_request):
        user = UserFactory.create()
        je = JournalEntryFactory.create(submitted_by=user)
        assert simple.simple_index(db_request) == {"projects": []}
        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)

    def test_with_results_no_serial(self, db_request):
        projects = [
            (x.name, x.normalized_name)
            for x in [ProjectFactory.create() for _ in range(3)]
        ]
        assert simple.simple_index(db_request) == {
            "projects": sorted(projects, key=lambda x: x[1])
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == "0"

    def test_with_results_with_serial(self, db_request):
        projects = [
            (x.name, x.normalized_name)
            for x in [ProjectFactory.create() for _ in range(3)]
        ]
        user = UserFactory.create()
        je = JournalEntryFactory.create(submitted_by=user)

        assert simple.simple_index(db_request) == {
            "projects": sorted(projects, key=lambda x: x[1])
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)


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
        assert pyramid_request.current_route_path.calls == [pretend.call(name="foo")]

    def test_no_files_no_serial(self, db_request):
        project = ProjectFactory.create()
        db_request.matchdict["name"] = project.normalized_name
        user = UserFactory.create()
        JournalEntryFactory.create(submitted_by=user)

        assert simple.simple_detail(project, db_request) == {
            "project": project,
            "files": [],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == "0"

    def test_no_files_with_serial(self, db_request):
        project = ProjectFactory.create()
        db_request.matchdict["name"] = project.normalized_name
        user = UserFactory.create()
        je = JournalEntryFactory.create(name=project.name, submitted_by=user)

        assert simple.simple_detail(project, db_request) == {
            "project": project,
            "files": [],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)

    def test_with_files_no_serial(self, db_request):
        project = ProjectFactory.create()
        releases = [ReleaseFactory.create(project=project) for _ in range(3)]
        files = [
            FileFactory.create(
                release=r, filename="{}-{}.tar.gz".format(project.name, r.version)
            )
            for r in releases
        ]
        # let's assert the result is ordered by string comparison of filename
        files = sorted(files, key=lambda key: key.filename)
        db_request.matchdict["name"] = project.normalized_name
        user = UserFactory.create()
        JournalEntryFactory.create(submitted_by=user)

        assert simple.simple_detail(project, db_request) == {
            "project": project,
            "files": files,
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == "0"

    def test_with_files_with_serial(self, db_request):
        project = ProjectFactory.create()
        releases = [ReleaseFactory.create(project=project) for _ in range(3)]
        files = [
            FileFactory.create(
                release=r, filename="{}-{}.tar.gz".format(project.name, r.version)
            )
            for r in releases
        ]
        # let's assert the result is ordered by string comparison of filename
        files = sorted(files, key=lambda key: key.filename)
        db_request.matchdict["name"] = project.normalized_name
        user = UserFactory.create()
        je = JournalEntryFactory.create(name=project.name, submitted_by=user)

        assert simple.simple_detail(project, db_request) == {
            "project": project,
            "files": files,
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)

    def test_with_files_with_version_multi_digit(self, db_request):
        project = ProjectFactory.create()
        release_versions = [
            "0.3.0rc1",
            "0.3.0",
            "0.3.0-post0",
            "0.14.0",
            "4.2.0",
            "24.2.0",
        ]
        releases = [
            ReleaseFactory.create(project=project, version=version)
            for version in release_versions
        ]

        tar_files = [
            FileFactory.create(
                release=r,
                filename="{}-{}.tar.gz".format(project.name, r.version),
                packagetype="sdist",
            )
            for r in releases
        ]
        wheel_files = [
            FileFactory.create(
                release=r,
                filename="{}-{}.whl".format(project.name, r.version),
                packagetype="bdist_wheel",
            )
            for r in releases
        ]
        egg_files = [
            FileFactory.create(
                release=r,
                filename="{}-{}.egg".format(project.name, r.version),
                packagetype="bdist_egg",
            )
            for r in releases
        ]

        files = []
        for files_release in zip(egg_files, tar_files, wheel_files):
            files += files_release

        db_request.matchdict["name"] = project.normalized_name
        user = UserFactory.create()
        je = JournalEntryFactory.create(name=project.name, submitted_by=user)

        assert simple.simple_detail(project, db_request) == {
            "project": project,
            "files": files,
        }

        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)
