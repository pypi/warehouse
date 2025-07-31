# SPDX-License-Identifier: Apache-2.0

from collections import OrderedDict

import pretend
import pytest

from pyramid.authorization import Allow, Authenticated
from pyramid.location import lineage

from warehouse.authnz import Permissions
from warehouse.macaroons import caveats
from warehouse.macaroons.models import Macaroon
from warehouse.oidc.models import GitHubPublisher
from warehouse.organizations.models import TeamProjectRoleType
from warehouse.packaging.models import (
    File,
    Project,
    ProjectFactory,
    ProjectMacaroonWarningAssociation,
    ReleaseURL,
)

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
                    Permissions.AdminProhibitedUsernameWrite,
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

    def test_acl_for_quarantined_project(self, db_session):
        """
        If a Project is quarantined, the Project ACL should disallow any modifications.
        """
        project = DBProjectFactory.create(lifecycle_status="quarantine-enter")
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

        _perms_read_and_upload = [
            Permissions.ProjectsRead,
            Permissions.ProjectsUpload,
        ]
        assert acls == [
            (
                Allow,
                "group:admins",
                (
                    Permissions.AdminDashboardSidebarRead,
                    Permissions.AdminObservationsRead,
                    Permissions.AdminObservationsWrite,
                    Permissions.AdminProhibitedProjectsWrite,
                    Permissions.AdminProhibitedUsernameWrite,
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
                (Allow, f"user:{owner1.user.id}", _perms_read_and_upload),
                (Allow, f"user:{owner2.user.id}", _perms_read_and_upload),
                (Allow, f"user:{owner3.user.id}", _perms_read_and_upload),
                (Allow, f"user:{owner4.user.id}", _perms_read_and_upload),
            ],
            key=lambda x: x[1],
        ) + sorted(
            [
                (Allow, f"user:{maintainer1.user.id}", _perms_read_and_upload),
                (Allow, f"user:{maintainer2.user.id}", _perms_read_and_upload),
            ],
            key=lambda x: x[1],
        )

    def test_acl_for_archived_project(self, db_session):
        """
        If a Project is archived, the Project ACL should disallow uploads.
        """
        project = DBProjectFactory.create(lifecycle_status="archived")
        owner1 = DBRoleFactory.create(project=project)
        owner2 = DBRoleFactory.create(project=project)

        # Maintainers should not appear in the ACLs, since they only have
        # upload permissions, and archived projects don't allow upload
        DBRoleFactory.create_batch(2, project=project, role_name="Maintainer")

        organization = DBOrganizationFactory.create()
        owner3 = DBOrganizationRoleFactory.create(organization=organization)
        DBOrganizationProjectFactory.create(organization=organization, project=project)

        team = DBTeamFactory.create()
        owner4 = DBTeamRoleFactory.create(team=team)
        DBTeamProjectRoleFactory.create(
            team=team, project=project, role_name=TeamProjectRoleType.Owner
        )

        # Publishers should not appear in the ACLs, since they only have upload
        # permissions, and archived projects don't allow upload
        GitHubPublisherFactory.create(projects=[project])

        acls = []
        for location in lineage(project):
            try:
                acl = location.__acl__
            except AttributeError:
                continue

            if acl and callable(acl):
                acl = acl()

            acls.extend(acl)

        _perms_read_and_write = [
            Permissions.ProjectsRead,
            Permissions.ProjectsWrite,
        ]
        assert acls == [
            (
                Allow,
                "group:admins",
                (
                    Permissions.AdminDashboardSidebarRead,
                    Permissions.AdminObservationsRead,
                    Permissions.AdminObservationsWrite,
                    Permissions.AdminProhibitedProjectsWrite,
                    Permissions.AdminProhibitedUsernameWrite,
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
                (Allow, f"user:{owner1.user.id}", _perms_read_and_write),
                (Allow, f"user:{owner2.user.id}", _perms_read_and_write),
                (Allow, f"user:{owner3.user.id}", _perms_read_and_write),
                (Allow, f"user:{owner4.user.id}", _perms_read_and_write),
            ],
            key=lambda x: x[1],
        )

    def test_repr(self, db_request):
        project = DBProjectFactory()
        assert isinstance(repr(project), str)

    def test_maintainers(self, db_session):
        project = DBProjectFactory.create()
        owner1 = DBRoleFactory.create(project=project)
        owner2 = DBRoleFactory.create(project=project)
        maintainer1 = DBRoleFactory.create(project=project, role_name="Maintainer")
        maintainer2 = DBRoleFactory.create(project=project, role_name="Maintainer")

        assert maintainer1.user in project.maintainers
        assert maintainer2.user in project.maintainers

        assert owner1.user not in project.maintainers
        assert owner2.user not in project.maintainers

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

    def test_deletion_project_with_macaroon_warning(self, db_session, macaroon_service):
        """
        When we remove a Project, ensure that we also remove any related
        warnings about the use of API tokens from the ProjectMacaroonWarningAssociation
        table
        """
        project = DBProjectFactory.create()
        owner = DBRoleFactory.create()
        raw_macaroon, macaroon = macaroon_service.create_macaroon(
            "fake location",
            "fake description",
            [caveats.RequestUser(user_id=str(owner.user.id))],
            user_id=owner.user.id,
        )

        db_session.add(
            ProjectMacaroonWarningAssociation(
                macaroon_id=macaroon.id,
                project_id=project.id,
            )
        )
        assert (
            db_session.query(ProjectMacaroonWarningAssociation)
            .filter_by(project_id=project.id)
            .count()
            == 1
        )

        db_session.delete(project)
        # Flush session to trigger any FK constraints
        db_session.flush()

        assert db_session.query(Project).filter_by(id=project.id).count() == 0
        assert (
            db_session.query(ProjectMacaroonWarningAssociation)
            .filter_by(project_id=project.id)
            .count()
            == 0
        )

    def test_deletion_macaroon_with_macaroon_warning(
        self, db_session, macaroon_service
    ):
        """
        When we remove a Macaroon, ensure that we also remove any related
        warnings about the use of API tokens from the ProjectMacaroonWarningAssociation
        table
        """
        project = DBProjectFactory.create()
        owner = DBRoleFactory.create()
        raw_macaroon, macaroon = macaroon_service.create_macaroon(
            "fake location",
            "fake description",
            [caveats.RequestUser(user_id=str(owner.user.id))],
            user_id=owner.user.id,
        )

        db_session.add(
            ProjectMacaroonWarningAssociation(
                macaroon_id=macaroon.id,
                project_id=project.id,
            )
        )
        assert (
            db_session.query(ProjectMacaroonWarningAssociation)
            .filter_by(macaroon_id=macaroon.id)
            .count()
            == 1
        )

        db_session.delete(macaroon)
        # Flush session to trigger any FK constraints
        db_session.flush()

        assert db_session.query(Macaroon).filter_by(id=macaroon.id).count() == 0
        assert (
            db_session.query(ProjectMacaroonWarningAssociation)
            .filter_by(macaroon_id=macaroon.id)
            .count()
            == 0
        )

    def test_active_and_yanked_releases(self, db_session):
        project = DBProjectFactory.create()
        active_release0 = DBReleaseFactory.create(project=project)
        active_release1 = DBReleaseFactory.create(project=project)
        yanked_release0 = DBReleaseFactory.create(project=project, yanked=True)

        assert len(project.active_releases) == len([active_release0, active_release1])
        assert len(project.yanked_releases) == len([yanked_release0])
        assert len(project.releases) == len(
            [active_release0, active_release1, yanked_release0]
        )


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
    def test_getattr(self, db_session):
        project = DBProjectFactory.create()
        release = DBReleaseFactory.create(project=project)
        file = DBFileFactory.create(
            release=release,
            filename=f"{release.project.name}-{release.version}.tar.gz",
            python_version="source",
        )

        assert release[file.filename] == file

    def test_getattr_invalid_file(self, db_session):
        project = DBProjectFactory.create()
        release = DBReleaseFactory.create(project=project)

        with pytest.raises(KeyError):
            # Well-formed filename, but the File doesn't actually exist.
            release[f"{release.project.name}-{release.version}.tar.gz"]

    def test_getattr_wrong_file_for_release(self, db_session):
        project = DBProjectFactory.create()
        release1 = DBReleaseFactory.create(project=project)
        release2 = DBReleaseFactory.create(project=project)
        file = DBFileFactory.create(
            release=release1,
            filename=f"{release1.project.name}-{release1.version}.tar.gz",
            python_version="source",
        )

        assert release1[file.filename] == file

        # Accessing a file through a different release does not work.
        with pytest.raises(KeyError):
            release2[file.filename]

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

    @pytest.mark.parametrize(
        "release_urls",
        [
            [
                ("Issues", "https://github.com/org/user/issues", True),
                ("Source", "https://github.com/org/user", True),
                ("Homepage", "https://example.com/", False),
                ("Download", "https://example.com/", False),
            ],
            [
                ("Issues", "https://github.com/org/user/issues", True),
                ("Source", "https://github.com/org/user", True),
                ("Homepage", "https://homepage.com/", False),
                ("Download", "https://download.com/", False),
            ],
            [
                ("Issues", "https://github.com/org/user/issues", True),
                ("Source", "https://github.com/org/user", True),
                ("Homepage", "https://homepage.com/", True),
                ("Download", "https://download.com/", True),
            ],
        ],
    )
    def test_urls_by_verify_status(self, db_session, release_urls):
        release = DBReleaseFactory.create(
            home_page="https://homepage.com", download_url="https://download.com"
        )
        for label, url, verified in release_urls:
            db_session.add(
                ReleaseURL(
                    release=release,
                    name=label,
                    url=url,
                    verified=verified,
                )
            )

        for verified_status in [True, False]:
            for label, url in release.urls_by_verify_status(
                verified=verified_status
            ).items():
                assert (label, url, verified_status) in release_urls

    @pytest.mark.parametrize(
        (
            "homepage_metadata_url",
            "download_metadata_url",
            "extra_url",
            "extra_url_verified",
        ),
        [
            (
                "https://homepage.com",
                "https://download.com",
                "https://example.com",
                True,
            ),
            (
                "https://homepage.com",
                "https://download.com",
                "https://homepage.com",
                True,
            ),
            (
                "https://homepage.com",
                "https://download.com",
                "https://homepage.com",
                False,
            ),
            (
                "https://homepage.com",
                "https://download.com",
                "https://download.com",
                True,
            ),
            (
                "https://homepage.com",
                "https://download.com",
                "https://download.com",
                False,
            ),
        ],
    )
    def test_urls_by_verify_status_with_metadata_urls(
        self,
        db_session,
        homepage_metadata_url,
        download_metadata_url,
        extra_url,
        extra_url_verified,
    ):
        release = DBReleaseFactory.create(
            home_page=homepage_metadata_url, download_url=download_metadata_url
        )
        db_session.add(
            ReleaseURL(
                release=release,
                name="extra_url",
                url=extra_url,
                verified=extra_url_verified,
            )
        )

        verified_urls = release.urls_by_verify_status(verified=True).values()
        unverified_urls = release.urls_by_verify_status(verified=False).values()

        # Homepage and Download URLs stored separately from the project URLs
        # are considered unverified, unless they are equal to URLs present in
        # `project_urls` that are verified.
        if extra_url_verified:
            assert extra_url in verified_urls
            if homepage_metadata_url != extra_url:
                assert homepage_metadata_url in unverified_urls
            if download_metadata_url != extra_url:
                assert download_metadata_url in unverified_urls
        else:
            assert extra_url in unverified_urls
            assert homepage_metadata_url in unverified_urls
            assert download_metadata_url in unverified_urls

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
                    Permissions.AdminProhibitedUsernameWrite,
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
        ("url", "expected"),
        [
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
    def test_verified_github_repo_info_url(self, db_session, url, expected):
        release = DBReleaseFactory.create()
        release.project_urls["Homepage"] = {"url": url, "verified": True}
        assert release.verified_github_repo_info_url == expected

    def test_verified_github_repo_info_url_is_none_without_verified_url(
        self,
        db_session,
    ):
        release = DBReleaseFactory.create()
        assert release.verified_github_repo_info_url is None

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
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
    def test_verified_github_open_issue_info_url(self, db_session, url, expected):
        release = DBReleaseFactory.create()
        release.project_urls["Homepage"] = {"url": url, "verified": True}
        assert release.verified_github_open_issue_info_url == expected

    def test_verified_github_open_issueo_info_url_is_none_without_verified_url(
        self,
        db_session,
    ):
        release = DBReleaseFactory.create()
        assert release.verified_github_open_issue_info_url is None

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            (
                "https://gitlab.com/someuser/someproject",
                "someuser/someproject",
            ),
            (
                "https://gitlab.com/someuser/someproject/",
                "someuser/someproject",
            ),
            (
                "https://gitlab.com/someuser/someproject/-/tree/stable-9",
                "someuser/someproject",
            ),
            (
                "https://www.gitlab.com/someuser/someproject",
                "someuser/someproject",
            ),
            ("https://gitlab.com/someuser/", None),
            ("https://google.com/pypi/warehouse/tree/main", None),
            ("https://google.com", None),
            ("incorrect url", None),
            (
                "https://gitlab.com/someuser/someproject.git",
                "someuser/someproject",
            ),
            (
                "https://www.gitlab.com/someuser/someproject.git/",
                "someuser/someproject",
            ),
            ("git@bitbucket.org:definex/dsgnutils.git", None),
        ],
    )
    def test_verified_gitlab_repository(self, db_session, url, expected):
        release = DBReleaseFactory.create()
        release.project_urls["Homepage"] = {"url": url, "verified": True}
        assert release.verified_gitlab_repository == expected

    def test_verified_gitlab_repository_is_none_without_verified_url(
        self,
        db_session,
    ):
        release = DBReleaseFactory.create()
        assert release.verified_gitlab_repository is None

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
        project = DBProjectFactory.create()
        release = DBReleaseFactory.create(project=project)

        with pytest.raises(RuntimeError):
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
