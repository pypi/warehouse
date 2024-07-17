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

from warehouse.legacy.api import draft

from ....common.db.accounts import UserFactory
from ....common.db.packaging import (
    FileFactory,
    JournalEntryFactory,
    ProjectFactory,
    ReleaseFactory,
)


class TestDraftIndex:
    def test_with_results_no_serial(self, db_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0", published=None)
        draft_project_dict = {project.name: release}
        assert draft.draft_index(draft_project_dict, db_request) == {
            "draft_project_dict": draft_project_dict
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == "0"

    def test_with_results_with_serial(self, db_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0", published=None)
        draft_project_dict = {project.name: release}
        user = UserFactory.create()
        je = JournalEntryFactory.create(submitted_by=user)

        assert draft.draft_index(draft_project_dict, db_request) == {
            "draft_project_dict": draft_project_dict
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)


class TestDraftDetail:
    def test_no_files_no_serial(self, db_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0", published=None)
        db_request.matchdict["name"] = project.normalized_name
        user = UserFactory.create()
        JournalEntryFactory.create(submitted_by=user)

        assert draft.draft_detail(release, db_request) == {
            "project": project,
            "files": [],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == "0"

    def test_no_files_with_serial(self, db_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0", published=None)
        db_request.matchdict["name"] = project.normalized_name
        user = UserFactory.create()
        je = JournalEntryFactory.create(name=project.name, submitted_by=user)

        assert draft.draft_detail(release, db_request) == {
            "project": project,
            "files": [],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)

    def test_with_files_no_serial(self, db_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0", published=None)
        files = [
            FileFactory.create(
                release=release,
                filename=f"{project.name}-{release.version}.tar.gz",
            )
        ]
        db_request.matchdict["name"] = project.normalized_name
        user = UserFactory.create()
        JournalEntryFactory.create(submitted_by=user)

        assert draft.draft_detail(release, db_request) == {
            "project": project,
            "files": files,
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == "0"

    def test_with_files_with_serial(self, db_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0", published=None)
        files = [
            FileFactory.create(
                release=release,
                filename=f"{project.name}-{release.version}.tar.gz",
            )
        ]
        db_request.matchdict["name"] = project.normalized_name
        user = UserFactory.create()
        je = JournalEntryFactory.create(name=project.name, submitted_by=user)

        assert draft.draft_detail(release, db_request) == {
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
            ReleaseFactory.create(project=project, version=version, published=None)
            for version in release_versions
        ]

        tar_files = [
            FileFactory.create(
                release=r,
                filename=f"{project.name}-{r.version}.tar.gz",
                packagetype="sdist",
            )
            for r in releases
        ]
        wheel_files = [
            FileFactory.create(
                release=r,
                filename=f"{project.name}-{r.version}.whl",
                packagetype="bdist_wheel",
            )
            for r in releases
        ]
        egg_files = [
            FileFactory.create(
                release=r,
                filename=f"{project.name}-{r.version}.egg",
                packagetype="bdist_egg",
            )
            for r in releases
        ]

        files = [
            list(files_release)
            for files_release in zip(egg_files, tar_files, wheel_files)
        ]

        db_request.matchdict["name"] = project.normalized_name
        user = UserFactory.create()
        je = JournalEntryFactory.create(name=project.name, submitted_by=user)

        for release, files_release in zip(releases, files):
            assert draft.draft_detail(release, db_request) == {
                "project": project,
                "files": files_release,
            }

        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)
