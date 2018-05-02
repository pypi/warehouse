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

from collections import OrderedDict

import pretend
import pytest

from pyramid.security import Allow

from warehouse.packaging.models import (
    ProjectFactory, Dependency, DependencyKind, File,
)

from ...common.db.packaging import (
    ProjectFactory as DBProjectFactory, ReleaseFactory as DBReleaseFactory,
    FileFactory as DBFileFactory, RoleFactory as DBRoleFactory,
)


class TestRole:

    def test_role_ordering(self, db_request):
        project = DBProjectFactory.create()
        owner_role = DBRoleFactory.create(
            project=project,
            role_name="Owner",
        )
        maintainer_role = DBRoleFactory.create(
            project=project,
            role_name="Maintainer",
        )
        assert max([maintainer_role, owner_role]) == owner_role


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

    def test_traversal_finds_canonical_version(self, db_request):
        project = DBProjectFactory.create()
        release = DBReleaseFactory.create(version='1.0', project=project)

        assert project['1.0.0'] == release

    def test_traversal_finds_canonical_version_if_multiple(self, db_request):
        project = DBProjectFactory.create()
        release = DBReleaseFactory.create(version='1.0.0', project=project)
        DBReleaseFactory.create(version='1.0', project=project)

        assert project['1.0.0'] == release

    def test_traversal_cant_find(self, db_request):
        project = DBProjectFactory.create()

        with pytest.raises(KeyError):
            project["1.0"]

    def test_traversal_cant_find_if_multiple(self, db_request):
        project = DBProjectFactory.create()
        DBReleaseFactory.create(version='1.0.0', project=project)
        DBReleaseFactory.create(version='1.0', project=project)

        with pytest.raises(KeyError):
            project["1"]

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
            (Allow, "group:admins", "admin"),
            (Allow, str(owner1.user.id), ["manage", "upload"]),
            (Allow, str(owner2.user.id), ["manage", "upload"]),
            (Allow, str(maintainer1.user.id), ["upload"]),
            (Allow, str(maintainer2.user.id), ["upload"]),
        ]


class TestRelease:

    def test_has_meta_true_with_keywords(self, db_session):
        release = DBReleaseFactory.create(keywords="foo, bar")
        assert release.has_meta

    def test_has_meta_true_with_author(self, db_session):
        release = DBReleaseFactory.create(author="Batman")
        assert release.has_meta

        release = DBReleaseFactory.create(author_email="wayne@gotham.ny")
        assert release.has_meta

    def test_has_meta_true_with_maintainer(self, db_session):
        release = DBReleaseFactory.create(maintainer="Spiderman")
        assert release.has_meta

        release = DBReleaseFactory.create(maintainer_email="peter@parker.mrvl")
        assert release.has_meta

    def test_has_meta_false(self, db_session):
        release = DBReleaseFactory.create()
        assert not release.has_meta

    @pytest.mark.parametrize(
        ("home_page", "download_url", "project_urls", "expected"),
        [
            (None, None, [], OrderedDict()),
            (
                "https://example.com/home/",
                None,
                [],
                OrderedDict([("Homepage", "https://example.com/home/")]),
            ),
            (
                None,
                "https://example.com/download/",
                [],
                OrderedDict([("Download", "https://example.com/download/")]),
            ),
            (
                "https://example.com/home/",
                "https://example.com/download/",
                [],
                OrderedDict([
                    ("Homepage", "https://example.com/home/"),
                    ("Download", "https://example.com/download/"),
                ]),
            ),
            (
                None,
                None,
                ["Source Code,https://example.com/source-code/"],
                OrderedDict([
                    ("Source Code", "https://example.com/source-code/"),
                ]),
            ),
            (
                None,
                None,
                ["Source Code, https://example.com/source-code/"],
                OrderedDict([
                    ("Source Code", "https://example.com/source-code/"),
                ]),
            ),
            (
                "https://example.com/home/",
                "https://example.com/download/",
                ["Source Code,https://example.com/source-code/"],
                OrderedDict([
                    ("Homepage", "https://example.com/home/"),
                    ("Source Code", "https://example.com/source-code/"),
                    ("Download", "https://example.com/download/"),
                ]),
            ),
            (
                "https://example.com/home/",
                "https://example.com/download/",
                [
                    "Homepage,https://example.com/home2/",
                    "Source Code,https://example.com/source-code/",
                ],
                OrderedDict([
                    ("Homepage", "https://example.com/home2/"),
                    ("Source Code", "https://example.com/source-code/"),
                    ("Download", "https://example.com/download/"),
                ]),
            ),
            (
                "https://example.com/home/",
                "https://example.com/download/",
                [
                    "Source Code,https://example.com/source-code/",
                    "Download,https://example.com/download2/",
                ],
                OrderedDict([
                    ("Homepage", "https://example.com/home/"),
                    ("Source Code", "https://example.com/source-code/"),
                    ("Download", "https://example.com/download2/"),
                ]),
            ),
            (
                "https://example.com/home/",
                "https://example.com/download/",
                [
                    "Homepage,https://example.com/home2/",
                    "Source Code,https://example.com/source-code/",
                    "Download,https://example.com/download2/",
                ],
                OrderedDict([
                    ("Homepage", "https://example.com/home2/"),
                    ("Source Code", "https://example.com/source-code/"),
                    ("Download", "https://example.com/download2/"),
                ]),
            ),
        ],
    )
    def test_urls(self, db_session, home_page, download_url, project_urls,
                  expected):
        release = DBReleaseFactory.create(
            home_page=home_page,
            download_url=download_url,
        )

        for urlspec in project_urls:
            db_session.add(
                Dependency(
                    name=release.project.name,
                    version=release.version,
                    kind=DependencyKind.project_url.value,
                    specifier=urlspec,
                )
            )

        # TODO: It'd be nice to test for the actual ordering here.
        assert dict(release.urls) == dict(expected)

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
        release = DBReleaseFactory.create(project=project)

        assert release.__acl__() == [
            (Allow, "group:admins", "admin"),
            (Allow, str(owner1.user.id), ["manage", "upload"]),
            (Allow, str(owner2.user.id), ["manage", "upload"]),
            (Allow, str(maintainer1.user.id), ["upload"]),
            (Allow, str(maintainer2.user.id), ["upload"]),
        ]

    @pytest.mark.parametrize(
        ("home_page", "expected"),
        [
            (None, None),
            (
                "https://github.com/pypa/warehouse",
                "https://api.github.com/repos/pypa/warehouse"
            ),
            (
                "https://github.com/pypa/warehouse/",
                "https://api.github.com/repos/pypa/warehouse"
            ),
            (
                "https://github.com/pypa/warehouse/tree/master",
                "https://api.github.com/repos/pypa/warehouse"
            ),
            (
                "https://www.github.com/pypa/warehouse",
                "https://api.github.com/repos/pypa/warehouse"
            ),
            (
                "https://github.com/pypa/",
                None
            ),
            (
                "https://google.com/pypa/warehouse/tree/master",
                None
            ),
            (
                "https://google.com",
                None
            ),
            (
                "incorrect url",
                None
            ),
        ],
    )
    def test_github_repo_info_url(self, db_session, home_page, expected):
        release = DBReleaseFactory.create(
            home_page=home_page
        )
        assert release.github_repo_info_url == expected


class TestFile:

    def test_requires_python(self, db_session):
        """ Attempt to write a File by setting requires_python directly,
            which should fail to validate (it should only be set in Release).
        """
        with pytest.raises(RuntimeError):
            project = DBProjectFactory.create()
            release = DBReleaseFactory.create(project=project)
            DBFileFactory.create(
                release=release,
                filename="{}-{}.tar.gz".format(project.name, release.version),
                python_version="source",
                requires_python="1.0"
            )

    def test_compute_paths(self, db_session):
        project = DBProjectFactory.create()
        release = DBReleaseFactory.create(project=project)
        rfile = DBFileFactory.create(
            release=release,
            filename="{}-{}.tar.gz".format(project.name, release.version),
            python_version="source",
        )

        expected = "/".join([
            rfile.blake2_256_digest[:2],
            rfile.blake2_256_digest[2:4],
            rfile.blake2_256_digest[4:],
            rfile.filename,
        ])

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

        expected = "/".join([
            rfile.blake2_256_digest[:2],
            rfile.blake2_256_digest[2:4],
            rfile.blake2_256_digest[4:],
            rfile.filename,
        ])

        results = (
            db_session.query(File.path, File.pgp_path)
            .filter(File.id == rfile.id)
            .limit(1)
            .one()
        )

        assert results == (expected, expected + ".asc")
