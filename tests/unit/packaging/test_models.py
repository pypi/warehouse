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

from pyramid.security import Allow

from warehouse.packaging.models import ProjectFactory, File

from ...common.db.packaging import (
    ProjectFactory as DBProjectFactory, ReleaseFactory as DBReleaseFactory,
    FileFactory as DBFileFactory, RoleFactory as DBRoleFactory,
)


class TestProjectFactory:

    @pytest.mark.parametrize(
        ("name", "normalized"),
        [
            ("foo", "foo"),
            ("Bar", "bar"),
        ],
    )
    def test_traversal_finds(self, db_request, name, normalized):
        project = DBProjectFactory.create(name=name)
        root = ProjectFactory(db_request)

        assert root[normalized] == project

    def test_travel_cant_find(self, db_request):
        project = DBProjectFactory.create()
        root = ProjectFactory(db_request)

        with pytest.raises(KeyError):
            root[project.name + "invalid"]


class TestProject:

    def test_traversal_finds(self, db_request):
        project = DBProjectFactory.create()
        release = DBReleaseFactory.create(project=project)

        assert project[release.version] == release

    def test_traversal_cant_find(self, db_request):
        project = DBProjectFactory.create()

        with pytest.raises(KeyError):
            project["1.0"]

    def test_doc_url_doesnt_exist(self, db_request):
        project = DBProjectFactory.create()
        assert project.documentation_url is None

    def test_doc_url(self, pyramid_config, db_request):
        db_request.route_url = pretend.call_recorder(
            lambda route, **kw: "/the/docs/url/"
        )

        project = DBProjectFactory.create(has_docs=True)

        assert project.documentation_url == "/the/docs/url/"
        assert db_request.route_url.calls == [
            pretend.call("legacy.docs", project=project.name),
        ]

    def test_acl(self, db_session):
        project = DBProjectFactory.create()
        owner1 = DBRoleFactory.create(project=project)
        owner2 = DBRoleFactory.create(project=project)
        maintainer1 = DBRoleFactory.create(
            project=project,
            role_name="Maintainer",
        )
        maintainer2 = DBRoleFactory.create(
            project=project,
            role_name="Maintainer",
        )

        assert project.__acl__() == [
            (Allow, owner1.user.id, ["upload"]),
            (Allow, owner2.user.id, ["upload"]),
            (Allow, maintainer1.user.id, ["upload"]),
            (Allow, maintainer2.user.id, ["upload"]),
        ]


class TestRelease:

    def test_has_meta_true_with_keywords(self, db_session):
        release = DBReleaseFactory.create(keywords="foo, bar")
        assert release.has_meta

    def test_has_meta_false(self, db_session):
        release = DBReleaseFactory.create()
        assert not release.has_meta


class TestFile:

    def test_compute_paths(self, db_session):
        project = DBProjectFactory.create()
        release = DBReleaseFactory.create(project=project)
        rfile = DBFileFactory.create(
            release=release,
            filename="{}-{}.tar.gz".format(project.name, release.version),
            python_version="source",
        )

        expected = "source/{}/{}/{}".format(
            project.name[0], project.name, rfile.filename,
        )

        assert rfile.path == expected
        assert rfile.pgp_path == expected + ".asc"

    def test_query_paths(self, db_session):
        project = DBProjectFactory.create()
        release = DBReleaseFactory.create(project=project)
        rfile = DBFileFactory.create(
            release=release,
            filename="{}-{}.tar.gz".format(project.name, release.version),
            python_version="source",
        )

        expected = "source/{}/{}/{}".format(
            project.name[0], project.name, rfile.filename,
        )

        results = (
            db_session.query(File.path, File.pgp_path)
            .filter(File.id == rfile.id)
            .limit(1)
            .one()
        )

        assert results == (expected, expected + ".asc")
