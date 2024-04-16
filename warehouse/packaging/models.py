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
from __future__ import annotations

import enum
import typing

from collections import OrderedDict
from uuid import UUID

import packaging.utils

from github_reserved_names import ALL as GITHUB_RESERVED_NAMES
from pyramid.authorization import Allow, Authenticated
from pyramid.threadlocal import get_current_request
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    FetchedValue,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    or_,
    orm,
    sql,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, ENUM, UUID as PG_UUID
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import (
    Mapped,
    attribute_keyed_dict,
    declared_attr,
    mapped_column,
    validates,
)
from urllib3.exceptions import LocationParseError
from urllib3.util import parse_url

from warehouse import db
from warehouse.accounts.models import User
from warehouse.authnz import Permissions
from warehouse.classifiers.models import Classifier
from warehouse.events.models import HasEvents
from warehouse.integrations.vulnerabilities.models import VulnerabilityRecord
from warehouse.observations.models import HasObservations
from warehouse.organizations.models import (
    Organization,
    OrganizationProject,
    OrganizationRole,
    OrganizationRoleType,
    Team,
    TeamProjectRole,
)
from warehouse.sitemap.models import SitemapMixin
from warehouse.utils import dotted_navigator, wheel
from warehouse.utils.attrs import make_repr
from warehouse.utils.db.types import bool_false, datetime_now

if typing.TYPE_CHECKING:
    from warehouse.oidc.models import OIDCPublisher


class Role(db.Model):
    __tablename__ = "roles"
    __table_args__ = (
        Index("roles_user_id_idx", "user_id"),
        Index("roles_project_id_idx", "project_id"),
        UniqueConstraint("user_id", "project_id", name="_roles_user_project_uc"),
    )

    __repr__ = make_repr("role_name")

    role_name: Mapped[str]
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", onupdate="CASCADE", ondelete="CASCADE"),
    )

    user: Mapped[User] = orm.relationship(lazy=False)
    project: Mapped[Project] = orm.relationship(lazy=False, back_populates="roles")


class RoleInvitationStatus(str, enum.Enum):
    Pending = "pending"
    Expired = "expired"


class RoleInvitation(db.Model):
    __tablename__ = "role_invitations"
    __table_args__ = (
        Index("role_invitations_user_id_idx", "user_id"),
        UniqueConstraint(
            "user_id", "project_id", name="_role_invitations_user_project_uc"
        ),
    )

    __repr__ = make_repr("invite_status", "user", "project")

    invite_status: Mapped[RoleInvitationStatus]
    token: Mapped[str]
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
        index=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", onupdate="CASCADE", ondelete="CASCADE"),
        index=True,
    )

    user: Mapped[User] = orm.relationship(lazy=False)
    project: Mapped[Project] = orm.relationship(lazy=False)


class ProjectFactory:
    def __init__(self, request):
        self.request = request

    def __getitem__(self, project):
        try:
            return (
                self.request.db.query(Project)
                .filter(Project.normalized_name == func.normalize_pep426_name(project))
                .one()
            )
        except NoResultFound:
            raise KeyError from None

    def __contains__(self, project):
        try:
            self[project]
        except KeyError:
            return False
        else:
            return True


class Project(SitemapMixin, HasEvents, HasObservations, db.Model):
    __tablename__ = "projects"
    __repr__ = make_repr("name")

    # TODO: Cannot update columns that are used in triggers.
    name: Mapped[str] = mapped_column(Text)
    normalized_name: Mapped[str] = mapped_column(
        unique=True,
        server_default=FetchedValue(),
        server_onupdate=FetchedValue(),
    )
    created: Mapped[datetime_now | None] = mapped_column(
        index=True,
    )
    has_docs: Mapped[bool | None]
    upload_limit: Mapped[int | None]
    total_size_limit: Mapped[int | None] = mapped_column(BigInteger)
    last_serial: Mapped[int] = mapped_column(server_default=sql.text("0"))
    total_size: Mapped[int | None] = mapped_column(
        BigInteger, server_default=sql.text("0")
    )

    oidc_publishers: Mapped[list[OIDCPublisher]] = orm.relationship(
        secondary="oidc_publisher_project_association",
        back_populates="projects",
        passive_deletes=True,
    )

    organization: Mapped[Organization] = orm.relationship(
        secondary=OrganizationProject.__table__,
        back_populates="projects",
        uselist=False,
        viewonly=True,
    )
    roles: Mapped[list[Role]] = orm.relationship(
        back_populates="project",
        passive_deletes=True,
    )
    team: Mapped[Team] = orm.relationship(
        secondary=TeamProjectRole.__table__,
        back_populates="projects",
        viewonly=True,
    )
    team_project_roles: Mapped[list[TeamProjectRole]] = orm.relationship(
        back_populates="project",
        passive_deletes=True,
    )
    users: Mapped[list[User]] = orm.relationship(
        secondary=Role.__table__, back_populates="projects", viewonly=True
    )
    releases: Mapped[list[Release]] = orm.relationship(
        cascade="all, delete-orphan",
        order_by=lambda: Release._pypi_ordering.desc(),
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'::text",
            name="projects_valid_name",
        ),
        CheckConstraint(
            "upload_limit <= 1073741824",  # 1.0 GiB == 1073741824 bytes
            name="projects_upload_limit_max_value",
        ),
        Index(
            "project_name_ultranormalized",
            func.ultranormalize_name(name),
        ),
    )

    def __getitem__(self, version):
        session = orm.object_session(self)
        canonical_version = packaging.utils.canonicalize_version(version)

        try:
            return (
                session.query(Release)
                .filter(
                    Release.project == self,
                    Release.canonical_version == canonical_version,
                )
                .one()
            )
        except MultipleResultsFound:
            # There are multiple releases of this project which have the same
            # canonical version that were uploaded before we checked for
            # canonical version equivalence, so return the exact match instead
            try:
                return (
                    session.query(Release)
                    .filter(Release.project == self, Release.version == version)
                    .one()
                )
            except NoResultFound:
                # There are multiple releases of this project which have the
                # same canonical version, but none that have the exact version
                # specified, so just 404
                raise KeyError from None
        except NoResultFound:
            raise KeyError from None

    def __acl__(self):
        session = orm.object_session(self)
        acls = [
            # TODO: Similar to `warehouse.accounts.models.User.__acl__`, we express the
            #       permissions here in terms of the permissions that the user has on
            #       the project. This is more complex, as add ACL Entries based on other
            #       criteria, such as the user's role in the project.
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
            (Allow, "group:observers", Permissions.APIObservationsAdd),
            (Allow, Authenticated, Permissions.SubmitMalwareObservation),
        ]

        # The project has zero or more OIDC publishers registered to it,
        # each of which serves as an identity with the ability to upload releases.
        for publisher in self.oidc_publishers:
            acls.append((Allow, f"oidc:{publisher.id}", [Permissions.ProjectsUpload]))

        # Get all of the users for this project.
        query = session.query(Role).filter(Role.project == self)
        query = query.options(orm.lazyload(Role.project))
        query = query.options(orm.lazyload(Role.user))
        permissions = {
            (role.user_id, "Administer" if role.role_name == "Owner" else "Upload")
            for role in query.all()
        }

        # Add all of the team members for this project.
        query = session.query(TeamProjectRole).filter(TeamProjectRole.project == self)
        query = query.options(orm.lazyload(TeamProjectRole.project))
        query = query.options(orm.lazyload(TeamProjectRole.team))
        for role in query.all():
            permissions |= {
                (user.id, "Administer" if role.role_name.value == "Owner" else "Upload")
                for user in role.team.members
            }

        # Add all organization owners for this project.
        if self.organization:
            query = session.query(OrganizationRole).filter(
                OrganizationRole.organization == self.organization,
                OrganizationRole.role_name == OrganizationRoleType.Owner,
            )
            query = query.options(orm.lazyload(OrganizationRole.organization))
            query = query.options(orm.lazyload(OrganizationRole.user))
            permissions |= {(role.user_id, "Administer") for role in query.all()}

        for user_id, permission_name in sorted(permissions, key=lambda x: (x[1], x[0])):
            if permission_name == "Administer":
                acls.append(
                    (
                        Allow,
                        f"user:{user_id}",
                        [
                            Permissions.ProjectsRead,
                            Permissions.ProjectsUpload,
                            Permissions.ProjectsWrite,
                        ],
                    )
                )
            else:
                acls.append((Allow, f"user:{user_id}", [Permissions.ProjectsUpload]))
        return acls

    @property
    def documentation_url(self):
        # TODO: Move this into the database and eliminate the use of the
        #       threadlocal here.
        request = get_current_request()

        # If the project doesn't have docs, then we'll just return a None here.
        if not self.has_docs:
            return

        return request.route_url("legacy.docs", project=self.name)

    @property
    def owners(self):
        """Return all users who are owners of the project."""
        owner_roles = (
            orm.object_session(self)
            .query(User.id)
            .join(Role.user)
            .filter(Role.role_name == "Owner", Role.project == self)
            .subquery()
        )
        return (
            orm.object_session(self)
            .query(User)
            .join(owner_roles, User.id == owner_roles.c.id)
            .all()
        )

    @property
    def all_versions(self):
        return (
            orm.object_session(self)
            .query(
                Release.version,
                Release.created,
                Release.is_prerelease,
                Release.yanked,
                Release.yanked_reason,
            )
            .filter(Release.project == self)
            .order_by(Release._pypi_ordering.desc())
            .all()
        )

    @property
    def latest_version(self):
        return (
            orm.object_session(self)
            .query(Release.version, Release.created, Release.is_prerelease)
            .filter(Release.project == self, Release.yanked.is_(False))
            .order_by(Release.is_prerelease.nullslast(), Release._pypi_ordering.desc())
            .first()
        )


class DependencyKind(enum.IntEnum):
    requires = 1
    provides = 2
    obsoletes = 3
    requires_dist = 4
    provides_dist = 5
    obsoletes_dist = 6
    requires_external = 7


class Dependency(db.Model):
    __tablename__ = "release_dependencies"
    __table_args__ = (
        Index("release_dependencies_release_kind_idx", "release_id", "kind"),
    )
    __repr__ = make_repr("release", "kind", "specifier")

    release_id: Mapped[UUID] = mapped_column(
        ForeignKey("releases.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    release: Mapped[Release] = orm.relationship(back_populates="dependencies")
    kind: Mapped[int | None]
    specifier: Mapped[str | None]


def _dependency_relation(kind):
    return orm.relationship(
        "Dependency",
        primaryjoin=lambda: sql.and_(
            Release.id == Dependency.release_id, Dependency.kind == kind.value
        ),
        viewonly=True,
    )


class Description(db.Model):
    __tablename__ = "release_descriptions"

    content_type: Mapped[str | None]
    raw: Mapped[str]
    html: Mapped[str]
    rendered_by: Mapped[str]

    release: Mapped[Release] = orm.relationship(back_populates="description")


class ReleaseURL(db.Model):
    __tablename__ = "release_urls"
    __table_args__ = (
        UniqueConstraint("release_id", "name"),
        CheckConstraint(
            "char_length(name) BETWEEN 1 AND 32",
            name="release_urls_valid_name",
        ),
    )
    __repr__ = make_repr("name", "url")

    release_id: Mapped[UUID] = mapped_column(
        ForeignKey("releases.id", onupdate="CASCADE", ondelete="CASCADE"),
        index=True,
    )
    release: Mapped[Release] = orm.relationship(back_populates="_project_urls")

    name: Mapped[str] = mapped_column(String(32))
    url: Mapped[str]


DynamicFieldsEnum = ENUM(
    "Platform",
    "Supported-Platform",
    "Summary",
    "Description",
    "Description-Content-Type",
    "Keywords",
    "Home-page",
    "Download-URL",
    "Author",
    "Author-email",
    "Maintainer",
    "Maintainer-email",
    "License",
    "Classifier",
    "Requires-Dist",
    "Requires-Python",
    "Requires-External",
    "Project-URL",
    "Provides-Extra",
    "Provides-Dist",
    "Obsoletes-Dist",
    name="release_dynamic_fields",
)


class Release(HasObservations, db.Model):
    __tablename__ = "releases"

    @declared_attr
    def __table_args__(cls):  # noqa
        return (
            Index("release_created_idx", cls.created.desc()),
            Index("release_project_created_idx", cls.project_id, cls.created.desc()),
            Index("release_version_idx", cls.version),
            Index("release_canonical_version_idx", cls.canonical_version),
            UniqueConstraint("project_id", "version"),
        )

    __repr__ = make_repr("project", "version")
    __parent__ = dotted_navigator("project")
    __name__ = dotted_navigator("version")

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    project: Mapped[Project] = orm.relationship(back_populates="releases")
    version: Mapped[str] = mapped_column(Text)
    canonical_version: Mapped[str] = mapped_column()
    is_prerelease: Mapped[bool_false]
    author: Mapped[str | None]
    author_email: Mapped[str | None]
    maintainer: Mapped[str | None]
    maintainer_email: Mapped[str | None]
    home_page: Mapped[str | None]
    license: Mapped[str | None]
    summary: Mapped[str | None]
    keywords: Mapped[str | None]
    platform: Mapped[str | None]
    download_url: Mapped[str | None]
    _pypi_ordering: Mapped[int | None]
    requires_python: Mapped[str | None] = mapped_column(Text)
    created: Mapped[datetime_now] = mapped_column()

    description_id: Mapped[UUID] = mapped_column(
        ForeignKey("release_descriptions.id", onupdate="CASCADE", ondelete="CASCADE"),
        index=True,
    )
    description: Mapped[Description] = orm.relationship(
        back_populates="release",
        cascade="all, delete-orphan",
        single_parent=True,
    )

    yanked: Mapped[bool_false]

    yanked_reason: Mapped[str] = mapped_column(server_default="")

    dynamic = Column(  # type: ignore[var-annotated]
        ARRAY(DynamicFieldsEnum),
        nullable=True,
        comment="Array of metadata fields marked as Dynamic (PEP 643/Metadata 2.2)",
    )

    _classifiers: Mapped[list[Classifier]] = orm.relationship(
        secondary="release_classifiers",
        order_by=Classifier.ordering,
        passive_deletes=True,
    )
    classifiers = association_proxy("_classifiers", "classifier")

    _project_urls: Mapped[list[ReleaseURL]] = orm.relationship(
        collection_class=attribute_keyed_dict("name"),
        cascade="all, delete-orphan",
        order_by=lambda: ReleaseURL.name.asc(),
        passive_deletes=True,
    )
    project_urls = association_proxy(
        "_project_urls",
        "url",
        creator=lambda k, v: ReleaseURL(name=k, url=v),
    )

    files: Mapped[list[File]] = orm.relationship(
        cascade="all, delete-orphan",
        lazy="dynamic",
        order_by=lambda: File.filename,
        passive_deletes=True,
    )

    dependencies: Mapped[list[Dependency]] = orm.relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    vulnerabilities: Mapped[list[VulnerabilityRecord]] = orm.relationship(
        back_populates="releases",
        secondary="release_vulnerabilities",
        passive_deletes=True,
    )

    _requires = _dependency_relation(DependencyKind.requires)
    requires = association_proxy("_requires", "specifier")

    _provides = _dependency_relation(DependencyKind.provides)
    provides = association_proxy("_provides", "specifier")

    _obsoletes = _dependency_relation(DependencyKind.obsoletes)
    obsoletes = association_proxy("_obsoletes", "specifier")

    _requires_dist = _dependency_relation(DependencyKind.requires_dist)
    requires_dist = association_proxy("_requires_dist", "specifier")

    _provides_dist = _dependency_relation(DependencyKind.provides_dist)
    provides_dist = association_proxy("_provides_dist", "specifier")

    provides_extra = Column(  # type: ignore[var-annotated]
        ARRAY(Text),
        nullable=True,
        comment="Array of extra names (PEP 566/685|Metadata 2.1/2.3)",
    )

    _obsoletes_dist = _dependency_relation(DependencyKind.obsoletes_dist)
    obsoletes_dist = association_proxy("_obsoletes_dist", "specifier")

    _requires_external = _dependency_relation(DependencyKind.requires_external)
    requires_external = association_proxy("_requires_external", "specifier")

    uploader_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="SET NULL"),
        index=True,
    )
    uploader: Mapped[User] = orm.relationship(User)
    uploaded_via: Mapped[str | None]

    @property
    def urls(self):
        _urls = OrderedDict()

        if self.home_page:
            _urls["Homepage"] = self.home_page
        if self.download_url:
            _urls["Download"] = self.download_url

        for name, url in self.project_urls.items():
            # avoid duplicating homepage/download links in case the same
            # url is specified in the pkginfo twice (in the Home-page
            # or Download-URL field and again in the Project-URL fields)
            comp_name = name.casefold().replace("-", "").replace("_", "")
            if comp_name == "homepage" and url == _urls.get("Homepage"):
                continue
            if comp_name == "downloadurl" and url == _urls.get("Download"):
                continue

            _urls[name] = url

        return _urls

    @staticmethod
    def get_user_name_and_repo_name(urls):
        for url in urls:
            try:
                parsed = parse_url(url)
            except LocationParseError:
                continue
            segments = parsed.path.strip("/").split("/") if parsed.path else []
            if parsed.netloc in {"github.com", "www.github.com"} and len(segments) >= 2:
                user_name, repo_name = segments[:2]
                if user_name in GITHUB_RESERVED_NAMES:
                    continue
                if repo_name.endswith(".git"):
                    repo_name = repo_name.removesuffix(".git")
                return user_name, repo_name
        return None, None

    @property
    def github_repo_info_url(self):
        user_name, repo_name = self.get_user_name_and_repo_name(self.urls.values())
        if user_name and repo_name:
            return f"https://api.github.com/repos/{user_name}/{repo_name}"

    @property
    def github_open_issue_info_url(self):
        user_name, repo_name = self.get_user_name_and_repo_name(self.urls.values())
        if user_name and repo_name:
            return (
                f"https://api.github.com/search/issues?q=repo:{user_name}/{repo_name}"
                "+type:issue+state:open&per_page=1"
            )

    @property
    def has_meta(self):
        return any(
            [
                self.license,
                self.keywords,
                self.author,
                self.author_email,
                self.maintainer,
                self.maintainer_email,
                self.requires_python,
            ]
        )

    @property
    def trusted_published(self) -> bool:
        """
        A Release can be considered published via a trusted publisher if
        **all** the Files in the release are published via a trusted publisher.
        """
        files = self.files.all()  # type: ignore[attr-defined]
        if not files:
            return False
        return all(file.uploaded_via_trusted_publisher for file in files)

    @property
    def is_source_verified(self) -> bool:
        """
        A Release can be considered source verified if it is trusted published
        and the source URL is the same of the trusted publisher.
        """
        urls = self.urls
        if not self.trusted_published or "Homepage" not in urls or urls["Homepage"] is None:
            return False

        return self.files.first().publisher_url == urls["Homepage"]


class PackageType(str, enum.Enum):
    bdist_dmg = "bdist_dmg"
    bdist_dumb = "bdist_dumb"
    bdist_egg = "bdist_egg"
    bdist_msi = "bdist_msi"
    bdist_rpm = "bdist_rpm"
    bdist_wheel = "bdist_wheel"
    bdist_wininst = "bdist_wininst"
    sdist = "sdist"


class File(HasEvents, db.Model):
    __tablename__ = "release_files"

    @declared_attr
    def __table_args__(cls):  # noqa
        return (
            CheckConstraint("sha256_digest ~* '^[A-F0-9]{64}$'"),
            CheckConstraint("blake2_256_digest ~* '^[A-F0-9]{64}$'"),
            Index(
                "release_files_single_sdist",
                "release_id",
                "packagetype",
                unique=True,
                postgresql_where=(
                    (cls.packagetype == "sdist")
                    & (cls.allow_multiple_sdist == False)  # noqa
                ),
            ),
            Index("release_files_release_id_idx", "release_id"),
            Index("release_files_archived_idx", "archived"),
            Index("release_files_cached_idx", "cached"),
        )

    release_id: Mapped[UUID] = mapped_column(
        ForeignKey("releases.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    release: Mapped[Release] = orm.relationship(back_populates="files")
    python_version: Mapped[str]
    requires_python: Mapped[str | None]
    packagetype: Mapped[PackageType] = mapped_column()
    comment_text: Mapped[str | None]
    filename: Mapped[str] = mapped_column(unique=True)
    path: Mapped[str] = mapped_column(unique=True)
    size: Mapped[int]
    md5_digest: Mapped[str] = mapped_column(unique=True)
    sha256_digest: Mapped[str] = mapped_column(CITEXT, unique=True)
    blake2_256_digest: Mapped[str] = mapped_column(CITEXT, unique=True)
    upload_time: Mapped[datetime_now]
    uploaded_via: Mapped[str | None]

    # PEP 658
    metadata_file_sha256_digest: Mapped[str | None] = mapped_column(CITEXT)
    metadata_file_blake2_256_digest: Mapped[str | None] = mapped_column(CITEXT)

    # We need this column to allow us to handle the currently existing "double"
    # sdists that exist in our database. Eventually we should try to get rid
    # of all of them and then remove this column.
    allow_multiple_sdist: Mapped[bool_false] = mapped_column()

    cached: Mapped[bool_false] = mapped_column(
        comment="If True, the object has been populated to our cache bucket.",
    )
    archived: Mapped[bool_false] = mapped_column(
        comment="If True, the object has been archived to our archival bucket.",
    )
    metadata_file_unbackfillable: Mapped[bool_false] = mapped_column(
        nullable=True,
        comment="If True, the metadata for the file cannot be backfilled.",
    )

    @property
    def uploaded_via_trusted_publisher(self) -> bool:
        """Return True if the file was uploaded via a trusted publisher."""
        return (self._get_trusted_publisher_events().count() > 0)

    def _get_trusted_publisher_events(self):
        return self.events.where(
                or_(
                    self.Event.additional[  # type: ignore[attr-defined]
                        "uploaded_via_trusted_publisher"
                    ].as_boolean(),
                    self.Event.additional["publisher_url"]  # type: ignore[attr-defined]
                    .as_string()
                    .is_not(None),
                )
            )
    
    @property
    def publisher_url(self) -> str:
        events = self._get_trusted_publisher_events()
        return events.first().additional["publisher_url"] if events.count() > 0 else None

    @hybrid_property
    def metadata_path(self):
        return self.path + ".metadata"

    @metadata_path.expression  # type: ignore
    def metadata_path(self):
        return func.concat(self.path, ".metadata")

    @validates("requires_python")
    def validates_requires_python(self, *args, **kwargs):
        raise RuntimeError("Cannot set File.requires_python")

    @property
    def pretty_wheel_tags(self) -> list[str]:
        return wheel.filename_to_pretty_tags(self.filename)


class Filename(db.ModelBase):
    __tablename__ = "file_registry"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(unique=True)


class ReleaseClassifiers(db.ModelBase):
    __tablename__ = "release_classifiers"
    __table_args__ = (
        Index("rel_class_trove_id_idx", "trove_id"),
        Index("rel_class_release_id_idx", "release_id"),
    )

    trove_id: Mapped[int] = mapped_column(
        ForeignKey("trove_classifiers.id"),
        primary_key=True,
    )
    release_id: Mapped[UUID] = mapped_column(
        PG_UUID,
        ForeignKey("releases.id", onupdate="CASCADE", ondelete="CASCADE"),
        primary_key=True,
    )


class JournalEntry(db.ModelBase):
    __tablename__ = "journals"

    @declared_attr
    def __table_args__(cls):  # noqa
        return (
            Index("journals_changelog", "submitted_date", "name", "version", "action"),
            Index("journals_name_idx", "name"),
            Index("journals_version_idx", "version"),
            Index("journals_submitted_by_idx", "submitted_by"),
            Index("journals_submitted_date_id_idx", cls.submitted_date, cls.id),
        )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str | None]
    action: Mapped[str | None]
    submitted_date: Mapped[datetime_now] = mapped_column()
    _submitted_by: Mapped[str | None] = mapped_column(
        "submitted_by",
        CITEXT,
        ForeignKey("users.username", onupdate="CASCADE"),
        nullable=True,
    )
    submitted_by: Mapped[User] = orm.relationship(lazy="raise_on_sql")


class ProhibitedProjectName(db.Model):
    __tablename__ = "prohibited_project_names"
    __table_args__ = (
        CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'::text",
            name="prohibited_project_valid_name",
        ),
    )

    __repr__ = make_repr("name")

    created: Mapped[datetime_now]
    name: Mapped[str] = mapped_column(unique=True)
    _prohibited_by = mapped_column(
        "prohibited_by", PG_UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    prohibited_by: Mapped[User] = orm.relationship()
    comment: Mapped[str] = mapped_column(server_default="")


class ProjectMacaroonWarningAssociation(db.Model):
    """
    Association table for Projects and Macaroons where a row (P, M) exists in
    the table iff all of the following statements are true:
    - M is an API-token Macaroon
    - M was used to upload a file to project P
    - P had a Trusted Publisher configured at the time of the upload
    - An email warning was sent to P's maintainers about the use of M

    In other words, this table tracks if we have warned a project's
    maintainers about a specific API token being used in spite of a Trusted
    Publisher being present. This is used in order to only send the warning
    once per project and API token.
    """

    __tablename__ = "project_macaroon_warning_association"

    macaroon_id = mapped_column(
        ForeignKey("macaroons.id", onupdate="CASCADE", ondelete="CASCADE"),
        primary_key=True,
    )
    project_id = mapped_column(ForeignKey("projects.id"), primary_key=True)
