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

import fs.errors
import pretend
import pytest

from warehouse.packaging.models import ProjectFactory, File

from ..common.db.packaging import (
    ProjectFactory as DBProjectFactory, ReleaseFactory as DBReleaseFactory,
    FileFactory as DBFileFactory,
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
        project = DBProjectFactory.create(
            session=db_request.db, name=name, normalized_name=normalized,
        )
        root = ProjectFactory(db_request)

        assert root[normalized] == project

    def test_travel_cant_find(self, db_request):
        project = DBProjectFactory.create(session=db_request.db)
        root = ProjectFactory(db_request)

        with pytest.raises(KeyError):
            root[project.name + "invalid"]


class TestProject:

    def test_traversal_finds(self, db_request):
        project = DBProjectFactory.create(session=db_request.db)
        release = DBReleaseFactory.create(
            session=db_request.db, project=project,
        )

        assert project[release.version] == release

    def test_traversal_cant_find(self, db_request):
        project = DBProjectFactory.create(session=db_request.db)

        with pytest.raises(KeyError):
            project["1.0"]

    def test_doc_url_doesnt_exist(self, pyramid_config, db_request):
        @pretend.call_recorder
        def exists(path):
            return False

        pyramid_config.registry["filesystems"] = {
            "documentation": pretend.stub(exists=exists),
        }

        project = DBProjectFactory.create(session=db_request.db)

        assert project.documentation_url is None
        assert exists.calls == [
            pretend.call("/".join([project.name, "index.html"])),
        ]

    def test_doc_url(self, pyramid_config, db_request):
        @pretend.call_recorder
        def exists(path):
            return True

        pyramid_config.registry["filesystems"] = {
            "documentation": pretend.stub(exists=exists),
        }

        db_request.route_url = pretend.call_recorder(
            lambda route, **kw: "/the/docs/url/"
        )

        project = DBProjectFactory.create(session=db_request.db)

        assert project.documentation_url == "/the/docs/url/"
        assert exists.calls == [
            pretend.call("/".join([project.name, "index.html"])),
        ]
        assert db_request.route_url.calls == [
            pretend.call("legacy.docs", project=project.name),
        ]


class TestFile:

    def test_compute_paths(self, db_session):
        project = DBProjectFactory.create(session=db_session)
        release = DBReleaseFactory.create(session=db_session, project=project)
        rfile = DBFileFactory.create(
            session=db_session,
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
        project = DBProjectFactory.create(session=db_session)
        release = DBReleaseFactory.create(session=db_session, project=project)
        rfile = DBFileFactory.create(
            session=db_session,
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

    @pytest.mark.parametrize("should_exist", [True, False])
    def test_has_pgp_signature(self, pyramid_config, db_session, should_exist):
        exister = pretend.call_recorder(lambda path: should_exist)
        pyramid_config.registry["filesystems"] = {
            "packages": pretend.stub(exists=exister),
        }

        project = DBProjectFactory.create(session=db_session)
        release = DBReleaseFactory.create(session=db_session, project=project)
        rfile = DBFileFactory.create(
            session=db_session,
            release=release,
            filename="{}-{}.tar.gz".format(project.name, release.version),
            python_version="source",
        )

        assert rfile.has_pgp_signature is should_exist
        assert exister.calls == [pretend.call(rfile.pgp_path)]

    def test_size_valid(self, pyramid_config, db_session):
        sizer = pretend.call_recorder(lambda path: 1934)
        pyramid_config.registry["filesystems"] = {
            "packages": pretend.stub(getsize=sizer),
        }

        project = DBProjectFactory.create(session=db_session)
        release = DBReleaseFactory.create(session=db_session, project=project)
        rfile = DBFileFactory.create(
            session=db_session,
            release=release,
            filename="{}-{}.tar.gz".format(project.name, release.version),
            python_version="source",
        )

        assert rfile.size == 1934
        assert sizer.calls == [pretend.call(rfile.path)]

    def test_size_returns_0_on_invalid(self, pyramid_config, db_session):
        @pretend.call_recorder
        def sizer(path):
            raise fs.errors.ResourceNotFoundError

        pyramid_config.registry["filesystems"] = {
            "packages": pretend.stub(getsize=sizer),
        }

        project = DBProjectFactory.create(session=db_session)
        release = DBReleaseFactory.create(session=db_session, project=project)
        rfile = DBFileFactory.create(
            session=db_session,
            release=release,
            filename="{}-{}.tar.gz".format(project.name, release.version),
            python_version="source",
        )

        assert rfile.size == 0
        assert sizer.calls == [pretend.call(rfile.path)]
