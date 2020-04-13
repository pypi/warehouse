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
from urllib.parse import urlparse

import packaging.utils

from citext import CIText
from pyramid.security import Allow
from pyramid.threadlocal import get_current_request
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    orm,
    sql,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import validates
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound

from warehouse import db
from warehouse.accounts.models import User
from warehouse.classifiers.models import Classifier
from warehouse.sitemap.models import SitemapMixin
from warehouse.utils import dotted_navigator
from warehouse.utils.attrs import make_repr


class Role(db.Model):

    __tablename__ = "roles"
    __table_args__ = (
        Index("roles_user_id_idx", "user_id"),
        UniqueConstraint("user_id", "project_id", name="_roles_user_project_uc"),
    )

    __repr__ = make_repr("role_name")

    role_name = Column(Text, nullable=False)
    user_id = Column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False
    )
    project_id = Column(
        ForeignKey("projects.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
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


class Project(SitemapMixin, db.Model):

    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'::text",
            name="projects_valid_name",
        ),
    )

    __repr__ = make_repr("name")

    name = Column(Text, nullable=False)
    normalized_name = orm.column_property(func.normalize_pep426_name(name))
    created = Column(
        DateTime(timezone=False),
        nullable=False,
        server_default=sql.func.now(),
        index=True,
    )
    has_docs = Column(Boolean)
    upload_limit = Column(Integer, nullable=True)
    last_serial = Column(Integer, nullable=False, server_default=sql.text("0"))
    zscore = Column(Float, nullable=True)

    total_size = Column(BigInteger, server_default=sql.text("0"))

    users = orm.relationship(User, secondary=Role.__table__, backref="projects")

    releases = orm.relationship(
        "Release",
        backref="project",
        cascade="all, delete-orphan",
        order_by=lambda: Release._pypi_ordering.desc(),
        passive_deletes=True,
    )

    events = orm.relationship(
        "ProjectEvent", backref="project", cascade="all, delete-orphan", lazy=True
    )

    def __getitem__(self, version):
        session = orm.object_session(self)
        canonical_version = packaging.utils.canonicalize_version(version)

        try:
            return (
                session.query(Release)
                .filter(
                    (Release.project == self)
                    & (Release.canonical_version == canonical_version)
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
                    .filter((Release.project == self) & (Release.version == version))
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

        # Get all of the users for this project.
        query = session.query(Role).filter(Role.project == self)
        query = query.options(orm.lazyload("project"))
        query = query.options(orm.joinedload("user").lazyload("emails"))
        query = query.join(User).order_by(User.id.asc())
        for role in sorted(
            query.all(), key=lambda x: ["Owner", "Maintainer"].index(x.role_name)
        ):
            if role.role_name == "Owner":
                acls.append((Allow, str(role.user.id), ["manage:project", "upload"]))
            else:
                acls.append((Allow, str(role.user.id), ["upload"]))
        return acls

    def record_event(self, *, tag, ip_address, additional=None):
        session = orm.object_session(self)
        event = ProjectEvent(
            project=self, tag=tag, ip_address=ip_address, additional=additional
        )
        session.add(event)
        session.flush()

        return event

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
    def all_versions(self):
        return (
            orm.object_session(self)
            .query(Release.version, Release.created, Release.is_prerelease)
            .filter(Release.project == self)
            .order_by(Release._pypi_ordering.desc())
            .all()
        )

    @property
    def latest_version(self):
        return (
            orm.object_session(self)
            .query(Release.version, Release.created, Release.is_prerelease)
            .filter(Release.project == self)
            .order_by(Release.is_prerelease.nullslast(), Release._pypi_ordering.desc())
            .first()
        )


class ProjectEvent(db.Model):
    __tablename__ = "project_events"

    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    tag = Column(String, nullable=False)
    time = Column(DateTime, nullable=False, server_default=sql.func.now())
    ip_address = Column(String, nullable=False)
    additional = Column(JSONB, nullable=True)


class DependencyKind(enum.IntEnum):

    requires = 1
    provides = 2
    obsoletes = 3
    requires_dist = 4
    provides_dist = 5
    obsoletes_dist = 6
    requires_external = 7

    # TODO: Move project URLs into their own table, since they are not actually
    #       a "dependency".
    project_url = 8


class Dependency(db.Model):

    __tablename__ = "release_dependencies"
    __table_args__ = (
        Index("release_dependencies_release_kind_idx", "release_id", "kind"),
    )
    __repr__ = make_repr("name", "version", "kind", "specifier")

    release_id = Column(
        ForeignKey("releases.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    kind = Column(Integer)
    specifier = Column(Text)


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

    content_type = Column(Text)
    raw = Column(Text, nullable=False)
    html = Column(Text, nullable=False)
    rendered_by = Column(Text, nullable=False)


class Release(db.Model):

    __tablename__ = "releases"

    @declared_attr
    def __table_args__(cls):  # noqa
        return (
            Index("release_created_idx", cls.created.desc()),
            Index("release_project_created_idx", cls.project_id, cls.created.desc()),
            Index("release_version_idx", cls.version),
            UniqueConstraint("project_id", "version"),
        )

    __repr__ = make_repr("project", "version")
    __parent__ = dotted_navigator("project")
    __name__ = dotted_navigator("version")

    project_id = Column(
        ForeignKey("projects.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    version = Column(Text, nullable=False)
    canonical_version = Column(Text, nullable=False)
    is_prerelease = orm.column_property(func.pep440_is_prerelease(version))
    author = Column(Text)
    author_email = Column(Text)
    maintainer = Column(Text)
    maintainer_email = Column(Text)
    home_page = Column(Text)
    license = Column(Text)
    summary = Column(Text)
    keywords = Column(Text)
    platform = Column(Text)
    download_url = Column(Text)
    _pypi_ordering = Column(Integer)
    requires_python = Column(Text)
    created = Column(
        DateTime(timezone=False), nullable=False, server_default=sql.func.now()
    )

    description_id = Column(
        ForeignKey("release_descriptions.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
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

    _classifiers = orm.relationship(
        Classifier,
        backref="project_releases",
        secondary=lambda: release_classifiers,
        order_by=Classifier.classifier,
        passive_deletes=True,
    )
    classifiers = association_proxy("_classifiers", "classifier")

    files = orm.relationship(
        "File",
        backref="release",
        cascade="all, delete-orphan",
        lazy="dynamic",
        order_by=lambda: File.filename,
        passive_deletes=True,
    )

    dependencies = orm.relationship(
        "Dependency",
        backref="release",
        cascade="all, delete-orphan",
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

    _project_urls = _dependency_relation(DependencyKind.project_url)
    project_urls = association_proxy("_project_urls", "specifier")

    uploader_id = Column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    uploader = orm.relationship(User)
    uploaded_via = Column(Text)

    @property
    def urls(self):
        _urls = OrderedDict()

        if self.home_page:
            _urls["Homepage"] = self.home_page
        if self.download_url:
            _urls["Download"] = self.download_url

        for urlspec in self.project_urls:
            name, _, url = urlspec.partition(",")
            name = name.strip()
            url = url.strip()
            if name and url:
                _urls[name] = url

        return _urls

    @property
    def github_repo_info_url(self):
        for url in self.urls.values():
            parsed = urlparse(url)
            segments = parsed.path.strip("/").split("/")
            if parsed.netloc in {"github.com", "www.github.com"} and len(segments) >= 2:
                user_name, repo_name = segments[:2]
                return f"https://api.github.com/repos/{user_name}/{repo_name}"

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


class File(db.Model):

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
        )

    release_id = Column(
        ForeignKey("releases.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    python_version = Column(Text)
    requires_python = Column(Text)
    packagetype = Column(
        Enum(
            "bdist_dmg",
            "bdist_dumb",
            "bdist_egg",
            "bdist_msi",
            "bdist_rpm",
            "bdist_wheel",
            "bdist_wininst",
            "sdist",
        )
    )
    comment_text = Column(Text)
    filename = Column(Text, unique=True)
    path = Column(Text, unique=True, nullable=False)
    size = Column(Integer)
    has_signature = Column(Boolean)
    md5_digest = Column(Text, unique=True, nullable=False)
    sha256_digest = Column(CIText, unique=True, nullable=False)
    blake2_256_digest = Column(CIText, unique=True, nullable=False)
    upload_time = Column(DateTime(timezone=False), server_default=func.now())
    uploaded_via = Column(Text)

    # We need this column to allow us to handle the currently existing "double"
    # sdists that exist in our database. Eventually we should try to get rid
    # of all of them and then remove this column.
    allow_multiple_sdist = Column(Boolean, nullable=False, server_default=sql.false())

    @hybrid_property
    def pgp_path(self):
        return self.path + ".asc"

    @pgp_path.expression
    def pgp_path(self):
        return func.concat(self.path, ".asc")

    @validates("requires_python")
    def validates_requires_python(self, *args, **kwargs):
        raise RuntimeError("Cannot set File.requires_python")


class Filename(db.ModelBase):

    __tablename__ = "file_registry"

    id = Column(Integer, primary_key=True, nullable=False)
    filename = Column(Text, unique=True, nullable=False)


release_classifiers = Table(
    "release_classifiers",
    db.metadata,
    Column(
        "release_id",
        ForeignKey("releases.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("trove_id", Integer(), ForeignKey("trove_classifiers.id")),
    Index("rel_class_trove_id_idx", "trove_id"),
    Index("rel_class_release_id_idx", "release_id"),
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

    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(Text)
    version = Column(Text)
    action = Column(Text)
    submitted_date = Column(
        DateTime(timezone=False), nullable=False, server_default=sql.func.now()
    )
    _submitted_by = Column(
        "submitted_by", CIText, ForeignKey("users.username", onupdate="CASCADE")
    )
    submitted_by = orm.relationship(User, lazy="raise_on_sql")
    submitted_from = Column(Text)


class BlacklistedProject(db.Model):

    __tablename__ = "blacklist"
    __table_args__ = (
        CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'::text",
            name="blacklist_valid_name",
        ),
    )

    __repr__ = make_repr("name")

    created = Column(
        DateTime(timezone=False), nullable=False, server_default=sql.func.now()
    )
    name = Column(Text, unique=True, nullable=False)
    _blacklisted_by = Column(
        "blacklisted_by", UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    blacklisted_by = orm.relationship(User)
    comment = Column(Text, nullable=False, server_default="")
