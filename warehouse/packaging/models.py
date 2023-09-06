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

import enum

from collections import OrderedDict

import packaging.utils

from github_reserved_names import ALL as GITHUB_RESERVED_NAMES
from pyramid.authorization import Allow
from pyramid.threadlocal import get_current_request
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    orm,
    sql,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import attribute_keyed_dict, declared_attr, mapped_column, validates
from urllib3.exceptions import LocationParseError
from urllib3.util import parse_url

from warehouse import db
from warehouse.accounts.models import User
from warehouse.classifiers.models import Classifier
from warehouse.events.models import HasEvents
from warehouse.integrations.vulnerabilities.models import VulnerabilityRecord
from warehouse.organizations.models import (
    Organization,
    OrganizationProject,
    OrganizationRole,
    OrganizationRoleType,
    TeamProjectRole,
)
from warehouse.sitemap.models import SitemapMixin
from warehouse.utils import dotted_navigator
from warehouse.utils.attrs import make_repr


class Role(db.Model):
    __tablename__ = "roles"
    __table_args__ = (
        Index("roles_user_id_idx", "user_id"),
        Index("roles_project_id_idx", "project_id"),
        UniqueConstraint("user_id", "project_id", name="_roles_user_project_uc"),
    )

    __repr__ = make_repr("role_name")

    role_name = mapped_column(Text, nullable=False)
    user_id = mapped_column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False
    )
    project_id = mapped_column(
        ForeignKey("projects.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )

    user = orm.relationship(User, lazy=False)
    project = orm.relationship("Project", lazy=False, back_populates="roles")


class RoleInvitationStatus(enum.Enum):
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

    invite_status = mapped_column(
        Enum(RoleInvitationStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    token = mapped_column(Text, nullable=False)
    user_id = mapped_column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id = mapped_column(
        ForeignKey("projects.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user = orm.relationship(User, lazy=False)
    project = orm.relationship("Project", lazy=False)


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


class TwoFactorRequireable:
    # Project owner requires 2FA for this project
    owners_require_2fa = mapped_column(
        Boolean, nullable=False, server_default=sql.false()
    )
    # PyPI requires 2FA for this project
    pypi_mandates_2fa = mapped_column(
        Boolean, nullable=False, server_default=sql.false()
    )

    @hybrid_property
    def two_factor_required(self):
        return self.owners_require_2fa | self.pypi_mandates_2fa


class Project(SitemapMixin, TwoFactorRequireable, HasEvents, db.Model):
    __tablename__ = "projects"
    __repr__ = make_repr("name")

    name = mapped_column(Text, nullable=False)
    normalized_name = mapped_column(
        Text,
        nullable=False,
        unique=True,
        server_default=FetchedValue(),
        server_onupdate=FetchedValue(),
    )
    created = mapped_column(
        DateTime(timezone=False),
        nullable=True,
        server_default=sql.func.now(),
        index=True,
    )
    has_docs = mapped_column(Boolean)
    upload_limit = mapped_column(Integer, nullable=True)
    total_size_limit = mapped_column(BigInteger, nullable=True)
    last_serial = mapped_column(Integer, nullable=False, server_default=sql.text("0"))
    total_size = mapped_column(BigInteger, server_default=sql.text("0"))

    organization = orm.relationship(
        Organization,
        secondary=OrganizationProject.__table__,
        back_populates="projects",
        uselist=False,
        viewonly=True,
    )
    roles = orm.relationship(
        Role,
        back_populates="project",
        passive_deletes=True,
    )
    team_project_roles = orm.relationship(
        TeamProjectRole,
        back_populates="project",
        passive_deletes=True,
    )
    users = orm.relationship(
        User, secondary=Role.__table__, backref="projects", viewonly=True
    )
    releases = orm.relationship(
        "Release",
        backref="project",
        cascade="all, delete-orphan",
        order_by=lambda: Release._pypi_ordering.desc(),  # type: ignore
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
            (Allow, "group:admins", "admin"),
            (Allow, "group:moderators", "moderator"),
        ]

        # The project has zero or more OIDC publishers registered to it,
        # each of which serves as an identity with the ability to upload releases.
        for publisher in self.oidc_publishers:
            acls.append((Allow, f"oidc:{publisher.id}", ["upload"]))

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
                acls.append((Allow, f"user:{user_id}", ["manage:project", "upload"]))
            else:
                acls.append((Allow, f"user:{user_id}", ["upload"]))
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
                Release.version, Release.created, Release.is_prerelease, Release.yanked
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

    release_id = mapped_column(
        ForeignKey("releases.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    kind = mapped_column(Integer)
    specifier = mapped_column(Text)


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

    content_type = mapped_column(Text)
    raw = mapped_column(Text, nullable=False)
    html = mapped_column(Text, nullable=False)
    rendered_by = mapped_column(Text, nullable=False)


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

    release_id = mapped_column(
        ForeignKey("releases.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = mapped_column(String(32), nullable=False)
    url = mapped_column(Text, nullable=False)


class Release(db.Model):
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

    project_id = mapped_column(
        ForeignKey("projects.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    version = mapped_column(Text, nullable=False)
    canonical_version = mapped_column(Text, nullable=False)
    is_prerelease = mapped_column(Boolean, nullable=False, server_default=sql.false())
    author = mapped_column(Text)
    author_email = mapped_column(Text)
    maintainer = mapped_column(Text)
    maintainer_email = mapped_column(Text)
    home_page = mapped_column(Text)
    license = mapped_column(Text)
    summary = mapped_column(Text)
    keywords = mapped_column(Text)
    platform = mapped_column(Text)
    download_url = mapped_column(Text)
    _pypi_ordering = mapped_column(Integer)
    requires_python = mapped_column(Text)
    created = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=sql.func.now()
    )

    description_id = mapped_column(
        ForeignKey("release_descriptions.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description = orm.relationship(
        "Description",
        backref=orm.backref(
            "release",
            cascade="all, delete-orphan",
            passive_deletes=True,
            passive_updates=True,
            single_parent=True,
            uselist=False,
        ),
    )

    yanked = mapped_column(Boolean, nullable=False, server_default=sql.false())

    yanked_reason = mapped_column(Text, nullable=False, server_default="")

    _classifiers = orm.relationship(
        Classifier,
        backref="project_releases",
        secondary="release_classifiers",
        order_by=Classifier.ordering,
        passive_deletes=True,
    )
    classifiers = association_proxy("_classifiers", "classifier")

    _project_urls = orm.relationship(
        ReleaseURL,
        backref="release",
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

    files = orm.relationship(
        "File",
        backref="release",
        cascade="all, delete-orphan",
        lazy="dynamic",
        order_by=lambda: File.filename,  # type: ignore
        passive_deletes=True,
    )

    dependencies = orm.relationship(
        "Dependency",
        backref="release",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    vulnerabilities = orm.relationship(
        VulnerabilityRecord,
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

    _obsoletes_dist = _dependency_relation(DependencyKind.obsoletes_dist)
    obsoletes_dist = association_proxy("_obsoletes_dist", "specifier")

    _requires_external = _dependency_relation(DependencyKind.requires_external)
    requires_external = association_proxy("_requires_external", "specifier")

    uploader_id = mapped_column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    uploader = orm.relationship(User)
    uploaded_via = mapped_column(Text)

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

    release_id = mapped_column(
        ForeignKey("releases.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    python_version = mapped_column(Text, nullable=False)
    requires_python = mapped_column(Text)
    packagetype = mapped_column(
        Enum(
            "bdist_dmg",
            "bdist_dumb",
            "bdist_egg",
            "bdist_msi",
            "bdist_rpm",
            "bdist_wheel",
            "bdist_wininst",
            "sdist",
        ),
        nullable=False,
    )
    comment_text = mapped_column(Text)
    filename = mapped_column(Text, unique=True, nullable=False)
    path = mapped_column(Text, unique=True, nullable=False)
    size = mapped_column(Integer, nullable=False)
    md5_digest = mapped_column(Text, unique=True, nullable=False)
    sha256_digest = mapped_column(CITEXT, unique=True, nullable=False)
    blake2_256_digest = mapped_column(CITEXT, unique=True, nullable=False)
    upload_time = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
    uploaded_via = mapped_column(Text)

    # PEP 658
    metadata_file_sha256_digest = mapped_column(CITEXT, nullable=True)
    metadata_file_blake2_256_digest = mapped_column(CITEXT, nullable=True)

    # We need this column to allow us to handle the currently existing "double"
    # sdists that exist in our database. Eventually we should try to get rid
    # of all of them and then remove this column.
    allow_multiple_sdist = mapped_column(
        Boolean, nullable=False, server_default=sql.false()
    )

    cached = mapped_column(
        Boolean,
        comment="If True, the object has been populated to our cache bucket.",
        nullable=False,
        server_default=sql.false(),
    )
    archived = mapped_column(
        Boolean,
        comment="If True, the object has been archived to our archival bucket.",
        nullable=False,
        server_default=sql.false(),
    )

    @hybrid_property
    def metadata_path(self):
        return self.path + ".metadata"

    @metadata_path.expression  # type: ignore
    def metadata_path(self):
        return func.concat(self.path, ".metadata")

    @validates("requires_python")
    def validates_requires_python(self, *args, **kwargs):
        raise RuntimeError("Cannot set File.requires_python")


class Filename(db.ModelBase):
    __tablename__ = "file_registry"

    id = mapped_column(Integer, primary_key=True, nullable=False)
    filename = mapped_column(Text, unique=True, nullable=False)


class ReleaseClassifiers(db.ModelBase):
    __tablename__ = "release_classifiers"
    __table_args__ = (
        Index("rel_class_trove_id_idx", "trove_id"),
        Index("rel_class_release_id_idx", "release_id"),
    )

    trove_id = mapped_column(
        Integer,
        ForeignKey("trove_classifiers.id"),
        primary_key=True,
    )
    release_id = mapped_column(
        UUID,
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

    id = mapped_column(Integer, primary_key=True, nullable=False)
    name = mapped_column(Text)
    version = mapped_column(Text)
    action = mapped_column(Text)
    submitted_date = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=sql.func.now()
    )
    _submitted_by = mapped_column(
        "submitted_by",
        CITEXT,
        ForeignKey("users.username", onupdate="CASCADE"),
        nullable=True,
    )
    submitted_by = orm.relationship(User, lazy="raise_on_sql")


class ProhibitedProjectName(db.Model):
    __tablename__ = "prohibited_project_names"
    __table_args__ = (
        CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'::text",
            name="prohibited_project_valid_name",
        ),
    )

    __repr__ = make_repr("name")

    created = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=sql.func.now()
    )
    name = mapped_column(Text, unique=True, nullable=False)
    _prohibited_by = mapped_column(
        "prohibited_by", UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    prohibited_by = orm.relationship(User)
    comment = mapped_column(Text, nullable=False, server_default="")
