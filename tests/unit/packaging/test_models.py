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

from pyramid.authorization import Allow, Authenticated
from pyramid.location import lineage

from warehouse.authnz import Permissions
from warehouse.oidc.models import GitHubPublisher
from warehouse.organizations.models import TeamProjectRoleType
from warehouse.packaging.models import File, Project, ProjectFactory, ReleaseURL

from ...common.db.oidc import GitHubPublisherFactory
from ...common.db.organizations import (
    OrganizationFactory as DBOrganizationFactory,
    OrganizationProjectFactory as DBOrganizationProjectFactory,
    OrganizationRoleFactory as DBOrganizationRoleFactory,
    TeamFactory as DBTeamFactory,
    TeamProjectRoleFactory as DBTeamProjectRoleFactory,
    TeamRoleFactory as DBTeamRoleFactory,
)
from ...common.db.packaging import (
    DependencyFactory as DBDependencyFactory,
    FileEventFactory as DBFileEventFactory,
    FileFactory as DBFileFactory,
    ProjectFactory as DBProjectFactory,
    ReleaseFactory as DBReleaseFactory,
    RoleFactory as DBRoleFactory,
    RoleInvitationFactory as DBRoleInvitationFactory,
)


class TestRole:
    def test_repr(self, db_request):
        role = DBRoleFactory()
        assert isinstance(repr(role), str)


class TestRoleInvitation:
    def test_repr(self, db_request):
        role_invitation = DBRoleInvitationFactory()
        assert isinstance(repr(role_invitation), str)


class TestProjectFactory:
    @pytest.mark.parametrize(("name", "normalized"), [("foo", "foo"), ("Bar", "bar")])
    def test_traversal_finds(self, db_request, name, normalized):
        project = DBProjectFactory.create(name=name)
        root = ProjectFactory(db_request)

        assert root[normalized] == project

    def test_travel_cant_find(self, db_request):
        project = DBProjectFactory.create()
        root = ProjectFactory(db_request)

        with pytest.raises(KeyError):
            root[project.name + "invalid"]

    def test_contains(self, db_request):
        DBProjectFactory.create(name="foo")
        root = ProjectFactory(db_request)

        assert "foo" in root
        assert "bar" not in root


class TestProject:
    def test_traversal_finds(self, db_request):
        project = DBProjectFactory.create()
        release = DBReleaseFactory.create(project=project)

        assert project[release.version] == release

    def test_traversal_finds_canonical_version(self, db_request):
        project = DBProjectFactory.create()
        release = DBReleaseFactory.create(version="1.0", project=project)

        assert project["1.0.0"] == release

    def test_traversal_finds_canonical_version_if_multiple(self, db_request):
        project = DBProjectFactory.create()
        release = DBReleaseFactory.create(version="1.0.0", project=project)
        DBReleaseFactory.create(version="1.0", project=project)

        assert project["1.0.0"] == release

    def test_traversal_cant_find(self, db_request):
        project = DBProjectFactory.create()

        with pytest.raises(KeyError):
            project["1.0"]

    def test_traversal_cant_find_if_multiple(self, db_request):
        project = DBProjectFactory.create()
        DBReleaseFactory.create(version="1.0.0", project=project)
        DBReleaseFactory.create(version="1.0", project=project)

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
            pretend.call("legacy.docs", project=project.name)
        ]

    def test_acl(self, db_session):
        project = DBProjectFactory.create()
        owner1 = DBRoleFactory.create(project=project)
        owner2 = DBRoleFactory.create(project=project)
        maintainer1 = DBRoleFactory.create(project=project, role_name="Maintainer")
        maintainer2 = DBRoleFactory.create(project=project, role_name="Maintainer")

        organization = DBOrganizationFactory.create()
        owner3 = DBOrganizationRoleFactory.create(organization=organization)
        DBOrganizationProjectFactory.create(organization=organization, project=project)

        team = DBTeamFactory.create()
        owner4 = DBTeamRoleFactory.create(team=team)
        DBTeamProjectRoleFactory.create(
            team=team, project=project, role_name=TeamProjectRoleType.Owner
        )

        publisher = GitHubPublisherFactory.create(projects=[project])

        acls = []
        for location in lineage(project):
            try:
                acl = location.__acl__
            except AttributeError:
                continue

            if acl and callable(acl):
                acl = acl()

            acls.extend(acl)

        assert acls == [
            (
                Allow,
                "group:admins",
                (
                    Permissions.AdminDashboardSidebarRead,
                    Permissions.AdminObservationsRead,
                    Permissions.AdminObservationsWrite,
                    Permissions.AdminProhibitedProjectsWrite,
                    Permissions.AdminProjectsDelete,
                    Permissions.AdminProjectsRead,
                    Permissions.AdminProjectsSetLimit,
                    Permissions.AdminProjectsWrite,
                    Permissions.AdminRoleAdd,
                    Permissions.AdminRoleDelete,
                ),
            ),
            (
                Allow,
                "group:moderators",
                (
                    Permissions.AdminDashboardSidebarRead,
                    Permissions.AdminObservationsRead,
                    Permissions.AdminObservationsWrite,
                    Permissions.AdminProjectsRead,
                    Permissions.AdminProjectsSetLimit,
                    Permissions.AdminRoleAdd,
                    Permissions.AdminRoleDelete,
                ),
            ),
            (
                Allow,
                "group:observers",
                Permissions.APIObservationsAdd,
            ),
            (
                Allow,
                Authenticated,
                Permissions.SubmitMalwareObservation,
            ),
        ] + sorted(
            [(Allow, f"oidc:{publisher.id}", [Permissions.ProjectsUpload])],
            key=lambda x: x[1],
        ) + sorted(
            [
                (
                    Allow,
                    f"user:{owner1.user.id}",
                    [
                        Permissions.ProjectsRead,
                        Permissions.ProjectsUpload,
                        Permissions.ProjectsWrite,
                    ],
                ),
                (
                    Allow,
                    f"user:{owner2.user.id}",
                    [
                        Permissions.ProjectsRead,
                        Permissions.ProjectsUpload,
                        Permissions.ProjectsWrite,
                    ],
                ),
                (
                    Allow,
                    f"user:{owner3.user.id}",
                    [
                        Permissions.ProjectsRead,
                        Permissions.ProjectsUpload,
                        Permissions.ProjectsWrite,
                    ],
                ),
                (
                    Allow,
                    f"user:{owner4.user.id}",
                    [
                        Permissions.ProjectsRead,
                        Permissions.ProjectsUpload,
                        Permissions.ProjectsWrite,
                    ],
                ),
            ],
            key=lambda x: x[1],
        ) + sorted(
            [
                (
                    Allow,
                    f"user:{maintainer1.user.id}",
                    [Permissions.ProjectsUpload],
                ),
                (
                    Allow,
                    f"user:{maintainer2.user.id}",
                    [Permissions.ProjectsUpload],
                ),
            ],
            key=lambda x: x[1],
        )

    def test_repr(self, db_request):
        project = DBProjectFactory()
        assert isinstance(repr(project), str)

    def test_deletion_with_trusted_publisher(self, db_session):
        """
        When we remove a Project, ensure that we also remove the related
        Publisher Association, but not the Publisher itself.
        """
        project = DBProjectFactory.create()
        publisher = GitHubPublisherFactory.create(projects=[project])

        db_session.delete(project)
        # Flush session to trigger any FK constraints
        db_session.flush()

        assert db_session.query(Project).filter_by(id=project.id).count() == 0
        assert db_session.query(GitHubPublisher).filter_by(id=publisher.id).count() == 1


class TestDependency:
    def test_repr(self, db_session):
        dependency = DBDependencyFactory.create()
        assert isinstance(repr(dependency), str)


class TestReleaseURL:
    def test_repr(self, db_session):
        release = DBReleaseFactory.create()
        release_url = ReleaseURL(
            release=release,
            name="Homepage",
            url="https://example.com/",
        )
        assert isinstance(repr(release_url), str)


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
                OrderedDict(
                    [
                        ("Homepage", "https://example.com/home/"),
                        ("Download", "https://example.com/download/"),
                    ]
                ),
            ),
            (
                None,
                None,
                ["Source Code,https://example.com/source-code/"],
                OrderedDict([("Source Code", "https://example.com/source-code/")]),
            ),
            (
                None,
                None,
                ["Source Code, https://example.com/source-code/"],
                OrderedDict([("Source Code", "https://example.com/source-code/")]),
            ),
            (
                "https://example.com/home/",
                "https://example.com/download/",
                ["Source Code,https://example.com/source-code/"],
                OrderedDict(
                    [
                        ("Homepage", "https://example.com/home/"),
                        ("Source Code", "https://example.com/source-code/"),
                        ("Download", "https://example.com/download/"),
                    ]
                ),
            ),
            (
                "https://example.com/home/",
                "https://example.com/download/",
                [
                    "Homepage,https://example.com/home2/",
                    "Source Code,https://example.com/source-code/",
                ],
                OrderedDict(
                    [
                        ("Homepage", "https://example.com/home2/"),
                        ("Source Code", "https://example.com/source-code/"),
                        ("Download", "https://example.com/download/"),
                    ]
                ),
            ),
            (
                "https://example.com/home/",
                "https://example.com/download/",
                [
                    "Source Code,https://example.com/source-code/",
                    "Download,https://example.com/download2/",
                ],
                OrderedDict(
                    [
                        ("Homepage", "https://example.com/home/"),
                        ("Source Code", "https://example.com/source-code/"),
                        ("Download", "https://example.com/download2/"),
                    ]
                ),
            ),
            # project_urls has more priority than home_page and download_url
            (
                "https://example.com/home/",
                "https://example.com/download/",
                [
                    "Homepage,https://example.com/home2/",
                    "Source Code,https://example.com/source-code/",
                    "Download,https://example.com/download2/",
                ],
                OrderedDict(
                    [
                        ("Homepage", "https://example.com/home2/"),
                        ("Source Code", "https://example.com/source-code/"),
                        ("Download", "https://example.com/download2/"),
                    ]
                ),
            ),
            # similar spellings of homepage/download label doesn't duplicate urls
            (
                "https://example.com/home/",
                "https://example.com/download/",
                [
                    "homepage, https://example.com/home/",
                    "download-URL ,https://example.com/download/",
                ],
                OrderedDict(
                    [
                        ("Homepage", "https://example.com/home/"),
                        ("Download", "https://example.com/download/"),
                    ]
                ),
            ),
            # the duplicate removal only happens if the urls are equal too!
            (
                "https://example.com/home1/",
                None,
                [
                    "homepage, https://example.com/home2/",
                ],
                OrderedDict(
                    [
                        ("Homepage", "https://example.com/home1/"),
                        ("homepage", "https://example.com/home2/"),
                    ]
                ),
            ),
        ],
    )
    def test_urls(self, db_session, home_page, download_url, project_urls, expected):
        release = DBReleaseFactory.create(
            home_page=home_page, download_url=download_url
        )

        for urlspec in project_urls:
            label, _, url = urlspec.partition(",")
            db_session.add(
                ReleaseURL(
                    release=release,
                    name=label.strip(),
                    url=url.strip(),
                )
            )

        # TODO: It'd be nice to test for the actual ordering here.
        assert dict(release.urls) == dict(expected)

    def test_acl(self, db_session):
        project = DBProjectFactory.create()
        owner1 = DBRoleFactory.create(project=project)
        owner2 = DBRoleFactory.create(project=project)
        maintainer1 = DBRoleFactory.create(project=project, role_name="Maintainer")
        maintainer2 = DBRoleFactory.create(project=project, role_name="Maintainer")
        release = DBReleaseFactory.create(project=project)

        acls = []
        for location in lineage(release):
            try:
                acl = location.__acl__
            except AttributeError:
                continue

            if acl and callable(acl):
                acl = acl()

            acls.extend(acl)

        assert acls == [
            (
                Allow,
                "group:admins",
                (
                    Permissions.AdminDashboardSidebarRead,
                    Permissions.AdminObservationsRead,
                    Permissions.AdminObservationsWrite,
                    Permissions.AdminProhibitedProjectsWrite,
                    Permissions.AdminProjectsDelete,
                    Permissions.AdminProjectsRead,
                    Permissions.AdminProjectsSetLimit,
                    Permissions.AdminProjectsWrite,
                    Permissions.AdminRoleAdd,
                    Permissions.AdminRoleDelete,
                ),
            ),
            (
                Allow,
                "group:moderators",
                (
                    Permissions.AdminDashboardSidebarRead,
                    Permissions.AdminObservationsRead,
                    Permissions.AdminObservationsWrite,
                    Permissions.AdminProjectsRead,
                    Permissions.AdminProjectsSetLimit,
                    Permissions.AdminRoleAdd,
                    Permissions.AdminRoleDelete,
                ),
            ),
            (
                Allow,
                "group:observers",
                Permissions.APIObservationsAdd,
            ),
            (
                Allow,
                Authenticated,
                Permissions.SubmitMalwareObservation,
            ),
        ] + sorted(
            [
                (
                    Allow,
                    f"user:{owner1.user.id}",
                    [
                        Permissions.ProjectsRead,
                        Permissions.ProjectsUpload,
                        Permissions.ProjectsWrite,
                    ],
                ),
                (
                    Allow,
                    f"user:{owner2.user.id}",
                    [
                        Permissions.ProjectsRead,
                        Permissions.ProjectsUpload,
                        Permissions.ProjectsWrite,
                    ],
                ),
            ],
            key=lambda x: x[1],
        ) + sorted(
            [
                (Allow, f"user:{maintainer1.user.id}", [Permissions.ProjectsUpload]),
                (Allow, f"user:{maintainer2.user.id}", [Permissions.ProjectsUpload]),
            ],
            key=lambda x: x[1],
        )

    @pytest.mark.parametrize(
        ("home_page", "expected"),
        [
            (None, None),
            (
                "https://github.com/pypi/warehouse",
                "https://api.github.com/repos/pypi/warehouse",
            ),
            (
                "https://github.com/pypi/warehouse/",
                "https://api.github.com/repos/pypi/warehouse",
            ),
            (
                "https://github.com/pypi/warehouse/tree/main",
                "https://api.github.com/repos/pypi/warehouse",
            ),
            (
                "https://www.github.com/pypi/warehouse",
                "https://api.github.com/repos/pypi/warehouse",
            ),
            ("https://github.com/pypa/", None),
            ("https://github.com/sponsors/pypa/", None),
            ("https://google.com/pypi/warehouse/tree/main", None),
            ("https://google.com", None),
            ("incorrect url", None),
            (
                "https://www.github.com/pypi/warehouse.git",
                "https://api.github.com/repos/pypi/warehouse",
            ),
            (
                "https://www.github.com/pypi/warehouse.git/",
                "https://api.github.com/repos/pypi/warehouse",
            ),
            ("git@bitbucket.org:definex/dsgnutils.git", None),
        ],
    )
    def test_github_repo_info_url(self, db_session, home_page, expected):
        release = DBReleaseFactory.create(home_page=home_page)
        assert release.github_repo_info_url == expected

    @pytest.mark.parametrize(
        ("home_page", "expected"),
        [
            (None, None),
            (
                "https://github.com/pypi/warehouse",
                "https://api.github.com/search/issues?q=repo:pypi/warehouse"
                "+type:issue+state:open&per_page=1",
            ),
            (
                "https://github.com/pypi/warehouse/",
                "https://api.github.com/search/issues?q=repo:pypi/warehouse+"
                "type:issue+state:open&per_page=1",
            ),
            (
                "https://github.com/pypi/warehouse/tree/main",
                "https://api.github.com/search/issues?q=repo:pypi/warehouse"
                "+type:issue+state:open&per_page=1",
            ),
            (
                "https://www.github.com/pypi/warehouse",
                "https://api.github.com/search/issues?q=repo:pypi/warehouse"
                "+type:issue+state:open&per_page=1",
            ),
            ("https://github.com/pypa/", None),
            ("https://github.com/sponsors/pypa/", None),
            ("https://google.com/pypi/warehouse/tree/main", None),
            ("https://google.com", None),
            ("incorrect url", None),
            (
                "https://www.github.com/pypi/warehouse.git",
                "https://api.github.com/search/issues?q=repo:pypi/warehouse"
                "+type:issue+state:open&per_page=1",
            ),
            (
                "https://www.github.com/pypi/warehouse.git/",
                "https://api.github.com/search/issues?q=repo:pypi/warehouse"
                "+type:issue+state:open&per_page=1",
            ),
        ],
    )
    def test_github_open_issue_info_url(self, db_session, home_page, expected):
        release = DBReleaseFactory.create(home_page=home_page)
        assert release.github_open_issue_info_url == expected

    def test_trusted_published_none(self, db_session):
        release = DBReleaseFactory.create()

        assert not release.trusted_published

    def test_trusted_published_all(self, db_session):
        release = DBReleaseFactory.create()
        release_file = DBFileFactory.create(
            release=release,
            filename=f"{release.project.name}-{release.version}.tar.gz",
            python_version="source",
        )
        DBFileEventFactory.create(
            source=release_file,
            tag="fake:event",
        )

        # Without a `publisher_url` value, not considered trusted published
        assert not release.trusted_published

        DBFileEventFactory.create(
            source=release_file,
            tag="fake:event",
            additional={"publisher_url": "https://fake/url"},
        )

        assert release.trusted_published

    def test_is_source_verified(self, db_session):
        release = DBReleaseFactory.create()
        release_file = DBFileFactory.create(
            release=release,
            filename=f"{release.project.name}-{release.version}.tar.gz",
            python_version="source",
        )
        DBFileEventFactory.create(
            source=release_file,
            tag="fake:event",
        )
        assert not release.is_source_verified

        DBFileEventFactory.create(
            source=release_file,
            tag="fake:event",
            additional={"publisher_url": "https://fake/url"},
        )
        assert not release.is_source_verified

        release.home_page = "xpto.com"
        assert not release.is_source_verified

        release.home_page = "https://fake/url"
        assert release.is_source_verified


    def test_trusted_published_mixed(self, db_session):
        release = DBReleaseFactory.create()
        rfile_1 = DBFileFactory.create(
            release=release,
            filename=f"{release.project.name}-{release.version}.tar.gz",
            python_version="source",
            packagetype="sdist",
        )
        rfile_2 = DBFileFactory.create(
            release=release,
            filename=f"{release.project.name}-{release.version}.whl",
            python_version="bdist_wheel",
            packagetype="bdist_wheel",
        )
        DBFileEventFactory.create(
            source=rfile_1,
            tag="fake:event",
        )
        DBFileEventFactory.create(
            source=rfile_2,
            tag="fake:event",
            additional={"publisher_url": "https://fake/url"},
        )

        assert not release.trusted_published

    def test_description_relationship(self, db_request):
        """When a Release is deleted, the Description is also deleted."""
        release = DBReleaseFactory.create()  # also creates a Description
        description = release.description

        db_request.db.delete(release)

        assert release in db_request.db.deleted
        assert description in db_request.db.deleted


class TestFile:
    def test_requires_python(self, db_session):
        """
        Attempt to write a File by setting requires_python directly, which
        should fail to validate (it should only be set in Release).
        """
        with pytest.raises(RuntimeError):
            project = DBProjectFactory.create()
            release = DBReleaseFactory.create(project=project)
            DBFileFactory.create(
                release=release,
                filename=f"{project.name}-{release.version}.tar.gz",
                python_version="source",
                requires_python="1.0",
            )

    def test_compute_paths(self, db_session):
        project = DBProjectFactory.create()
        release = DBReleaseFactory.create(project=project)
        rfile = DBFileFactory.create(
            release=release,
            filename=f"{project.name}-{release.version}.tar.gz",
            python_version="source",
        )

        expected = "/".join(
            [
                rfile.blake2_256_digest[:2],
                rfile.blake2_256_digest[2:4],
                rfile.blake2_256_digest[4:],
                rfile.filename,
            ]
        )

        assert rfile.path == expected
        assert rfile.metadata_path == expected + ".metadata"

    def test_query_paths(self, db_session):
        project = DBProjectFactory.create()
        release = DBReleaseFactory.create(project=project)
        rfile = DBFileFactory.create(
            release=release,
            filename=f"{project.name}-{release.version}.tar.gz",
            python_version="source",
        )

        expected = "/".join(
            [
                rfile.blake2_256_digest[:2],
                rfile.blake2_256_digest[2:4],
                rfile.blake2_256_digest[4:],
                rfile.filename,
            ]
        )

        results = (
            db_session.query(File.path, File.metadata_path)
            .filter(File.id == rfile.id)
            .limit(1)
            .one()
        )

        assert results == (expected, expected + ".metadata")

    def test_published_via_trusted_publisher_from_publisher_url(self, db_session):
        project = DBProjectFactory.create()
        release = DBReleaseFactory.create(project=project)
        rfile = DBFileFactory.create(
            release=release,
            filename=f"{project.name}-{release.version}.tar.gz",
            python_version="source",
        )
        DBFileEventFactory.create(
            source=rfile,
            tag="fake:event",
        )

        # Without the `publisher_url` key, not considered trusted published
        assert not rfile.uploaded_via_trusted_publisher

        DBFileEventFactory.create(
            source=rfile,
            tag="fake:event",
            additional={
                "publisher_url": "https://fake/url",
                "uploaded_via_trusted_publisher": False,
            },
        )

        assert rfile.uploaded_via_trusted_publisher

    def test_published_via_trusted_publisher_from_uploaded_via_trusted_publisher(
        self, db_session
    ):
        project = DBProjectFactory.create()
        release = DBReleaseFactory.create(project=project)
        rfile = DBFileFactory.create(
            release=release,
            filename=f"{project.name}-{release.version}.tar.gz",
            python_version="source",
        )
        DBFileEventFactory.create(
            source=rfile,
            tag="fake:event",
        )

        # Without `uploaded_via_trusted_publisher` being true,
        # not considered trusted published
        assert not rfile.uploaded_via_trusted_publisher

        DBFileEventFactory.create(
            source=rfile,
            tag="fake:event",
            additional={"publisher_url": None, "uploaded_via_trusted_publisher": True},
        )

        assert rfile.uploaded_via_trusted_publisher

    def test_pretty_wheel_tags(self, db_session):
        project = DBProjectFactory.create()
        release = DBReleaseFactory.create(project=project)
        rfile = DBFileFactory.create(
            release=release, filename=f"{project.name}-{release.version}.tar.gz"
        )

        assert rfile.pretty_wheel_tags == ["Source"]
