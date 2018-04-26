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
    CheckConstraint, Column, Enum, ForeignKey, ForeignKeyConstraint, Index,
    Boolean, DateTime, Integer, Float, Table, Text,
)
from sqlalchemy import func, orm, sql
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import validates
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.hybrid import hybrid_property

from warehouse import db
from warehouse.accounts.models import User
from warehouse.classifiers.models import Classifier
from warehouse.sitemap.models import SitemapMixin
from warehouse.utils.attrs import make_repr


class Role(db.Model):

    __tablename__ = "roles"
    __table_args__ = (
        Index("roles_pack_name_idx", "package_name"),
        Index("roles_user_name_idx", "user_name"),
    )

    __repr__ = make_repr("role_name", "user_name", "package_name")

    role_name = Column(Text)
    user_name = Column(
        CIText,
        ForeignKey(
            "accounts_user.username",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
    )
    package_name = Column(
        Text,
        ForeignKey("packages.name", onupdate="CASCADE", ondelete="CASCADE"),
    )

    user = orm.relationship(User, lazy=False)
    project = orm.relationship("Project", lazy=False)

    def __gt__(self, other):
        '''
        Temporary hack to allow us to only display the 'highest' role when
        there are multiple for a given user

        TODO: This should be removed when fixing GH-2745.
        '''
        order = ['Maintainer', 'Owner']  # from lowest to highest
        return order.index(self.role_name) > order.index(other.role_name)


class ProjectFactory:

    def __init__(self, request):
        self.request = request

    def __getitem__(self, project):
        try:
            return self.request.db.query(Project).filter(
                Project.normalized_name == func.normalize_pep426_name(project)
            ).one()
        except NoResultFound:
            raise KeyError from None


class Project(SitemapMixin, db.ModelBase):

    __tablename__ = "packages"
    __table_args__ = (
        CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'::text",
            name="packages_valid_name",
        ),
    )

    __repr__ = make_repr("name")

    name = Column(Text, primary_key=True, nullable=False)
    normalized_name = orm.column_property(func.normalize_pep426_name(name))
    stable_version = Column(Text)
    autohide = Column(Boolean, server_default=sql.true())
    comments = Column(Boolean, server_default=sql.true())
    bugtrack_url = Column(Text)
    hosting_mode = Column(Text, nullable=False, server_default="pypi-only")
    created = Column(
        DateTime(timezone=False),
        nullable=False,
        server_default=sql.func.now(),
    )
    has_docs = Column(Boolean)
    upload_limit = Column(Integer, nullable=True)
    last_serial = Column(Integer, nullable=False, server_default=sql.text("0"))
    allow_legacy_files = Column(
        Boolean,
        nullable=False,
        server_default=sql.false(),
    )
    zscore = Column(Float, nullable=True)

    users = orm.relationship(
        User,
        secondary=Role.__table__,
        backref="projects",
    )

    releases = orm.relationship(
        "Release",
        backref="project",
        cascade="all, delete-orphan",
        order_by=lambda: Release._pypi_ordering.desc(),
        passive_deletes=True,
    )

    def __getitem__(self, version):
        session = orm.object_session(self)
        canonical_version = packaging.utils.canonicalize_version(version)

        try:
            return (
                session.query(Release)
                .filter(
                    (Release.project == self) &
                    (Release.canonical_version == canonical_version)
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
                    .filter(
                        (Release.project == self) &
                        (Release.version == version)
                    )
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
        ]

        # Get all of the users for this project.
        query = session.query(Role).filter(Role.project == self)
        query = query.options(orm.lazyload("project"))
        query = query.options(orm.joinedload("user").lazyload("emails"))
        for role in sorted(
                query.all(),
                key=lambda x: ["Owner", "Maintainer"].index(x.role_name)):
            if role.role_name == "Owner":
                acls.append((Allow, str(role.user.id), ["manage", "upload"]))
            else:
                acls.append((Allow, str(role.user.id), ["upload"]))
        return acls

    @property
    def documentation_url(self):
        # TODO: Move this into the database and elimnate the use of the
        #       threadlocal here.
        request = get_current_request()

        # If the project doesn't have docs, then we'll just return a None here.
        if not self.has_docs:
            return

        return request.route_url("legacy.docs", project=self.name)

    @property
    def all_versions(self):
        return (orm.object_session(self)
                   .query(
                       Release.version,
                       Release.created,
                       Release.is_prerelease)
                   .filter(Release.project == self)
                   .order_by(Release._pypi_ordering.desc())
                   .all())

    @property
    def latest_version(self):
        return (orm.object_session(self)
                   .query(
                       Release.version,
                       Release.created,
                       Release.is_prerelease)
                   .filter(Release.project == self)
                   .order_by(
                       Release.is_prerelease.nullslast(),
                       Release._pypi_ordering.desc())
                   .first())


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
        Index("rel_dep_name_idx", "name"),
        Index("rel_dep_name_version_idx", "name", "version"),
        Index("rel_dep_name_version_kind_idx", "name", "version", "kind"),
        ForeignKeyConstraint(
            ["name", "version"],
            ["releases.name", "releases.version"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
    )
    __repr__ = make_repr("name", "version", "kind", "specifier")

    name = Column(Text)
    version = Column(Text)
    kind = Column(Integer)
    specifier = Column(Text)


def _dependency_relation(kind):
    return orm.relationship(
        "Dependency",
        primaryjoin=lambda: sql.and_(
            Release.name == Dependency.name,
            Release.version == Dependency.version,
            Dependency.kind == kind.value,
        ),
        viewonly=True,
    )


class Release(db.ModelBase):

    __tablename__ = "releases"

    @declared_attr
    def __table_args__(cls):  # noqa
        return (
            Index("release_created_idx", cls.created.desc()),
            Index("release_name_created_idx", cls.name, cls.created.desc()),
            Index("release_name_idx", cls.name),
            Index("release_pypi_hidden_idx", cls._pypi_hidden),
            Index("release_version_idx", cls.version),
        )

    __repr__ = make_repr("name", "version")

    name = Column(
        Text,
        ForeignKey("packages.name", onupdate="CASCADE", ondelete="CASCADE"),
        primary_key=True,
    )
    version = Column(Text, primary_key=True)
    canonical_version = Column(Text, nullable=False)
    is_prerelease = orm.column_property(func.pep440_is_prerelease(version))
    author = Column(Text)
    author_email = Column(Text)
    maintainer = Column(Text)
    maintainer_email = Column(Text)
    home_page = Column(Text)
    license = Column(Text)
    summary = Column(Text)
    description_content_type = Column(Text)
    keywords = Column(Text)
    platform = Column(Text)
    download_url = Column(Text)
    _pypi_ordering = Column(Integer)
    _pypi_hidden = Column(Boolean)
    cheesecake_installability_id = Column(
        Integer,
        ForeignKey("cheesecake_main_indices.id"),
    )
    cheesecake_documentation_id = Column(
        Integer,
        ForeignKey("cheesecake_main_indices.id"),
    )
    cheesecake_code_kwalitee_id = Column(
        Integer,
        ForeignKey("cheesecake_main_indices.id"),
    )
    requires_python = Column(Text)
    description_from_readme = Column(Boolean)
    created = Column(
        DateTime(timezone=False),
        nullable=False,
        server_default=sql.func.now(),
    )

    # We defer this column because it is a very large column (it can be MB in
    # size) and we very rarely actually want to access it. Typically we only
    # need it when rendering the page for a single project, but many of our
    # queries only need to access a few of the attributes of a Release. Instead
    # of playing whack-a-mole and using load_only() or defer() on each of
    # those queries, deferring this here makes the default case more
    # performant.
    description = orm.deferred(Column(Text))

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

    dependencies = orm.relationship("Dependency")

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

    uploader = orm.relationship(
        "User",
        secondary=lambda: JournalEntry.__table__,
        primaryjoin=lambda: (
            (JournalEntry.name == orm.foreign(Release.name)) &
            (JournalEntry.version == orm.foreign(Release.version)) &
            (JournalEntry.action == "new release")),
        secondaryjoin=lambda: (
            (User.username == orm.foreign(JournalEntry._submitted_by))
        ),
        order_by=lambda: JournalEntry.id.desc(),
        # TODO: We have uselist=False here which raises a warning because
        # multiple items were returned. This should only be temporary because
        # we should add a nullable FK to JournalEntry so we don't need to rely
        # on ordering and implicitly selecting the first object to make this
        # happen,
        uselist=False,
        viewonly=True,
    )

    def __acl__(self):
        session = orm.object_session(self)
        acls = [
            (Allow, "group:admins", "admin"),
        ]

        # Get all of the users for this project.
        query = session.query(Role).filter(Role.project == self)
        query = query.options(orm.lazyload("project"))
        query = query.options(orm.joinedload("user").lazyload("emails"))
        for role in sorted(
                query.all(),
                key=lambda x: ["Owner", "Maintainer"].index(x.role_name)):
            if role.role_name == "Owner":
                acls.append((Allow, str(role.user.id), ["manage", "upload"]))
            else:
                acls.append((Allow, str(role.user.id), ["upload"]))
        return acls

    @property
    def urls(self):
        _urls = OrderedDict()

        if self.home_page:
            _urls["Homepage"] = self.home_page

        for urlspec in self.project_urls:
            name, url = [x.strip() for x in urlspec.split(",", 1)]
            _urls[name] = url

        if self.download_url and "Download" not in _urls:
            _urls["Download"] = self.download_url

        return _urls

    @property
    def github_repo_info_url(self):
        for parsed in [urlparse(url) for url in self.urls.values()]:
            segments = parsed.path.strip('/').rstrip('/').split('/')
            if (parsed.netloc == 'github.com' or
                    parsed.netloc == 'www.github.com') and len(segments) >= 2:
                user_name, repo_name = segments[:2]
                return f"https://api.github.com/repos/{user_name}/{repo_name}"

    @property
    def has_meta(self):
        return any([self.license,
                    self.keywords,
                    self.author, self.author_email,
                    self.maintainer, self.maintainer_email,
                    self.requires_python])


class File(db.Model):

    __tablename__ = "release_files"

    @declared_attr
    def __table_args__(cls):  # noqa
        return (
            ForeignKeyConstraint(
                ["name", "version"],
                ["releases.name", "releases.version"],
                onupdate="CASCADE",
                ondelete="CASCADE",
            ),

            CheckConstraint("sha256_digest ~* '^[A-F0-9]{64}$'"),
            CheckConstraint("blake2_256_digest ~* '^[A-F0-9]{64}$'"),

            Index("release_files_name_version_idx", "name", "version"),
            Index("release_files_packagetype_idx", "packagetype"),
            Index("release_files_version_idx", "version"),
            Index(
                "release_files_single_sdist",
                "name",
                "version",
                "packagetype",
                unique=True,
                postgresql_where=(
                    (cls.packagetype == 'sdist') &
                    (cls.allow_multiple_sdist == False)  # noqa
                ),
            ),
        )

    name = Column(Text)
    version = Column(Text)
    python_version = Column(Text)
    requires_python = Column(Text)
    packagetype = Column(
        Enum(
            "bdist_dmg", "bdist_dumb", "bdist_egg", "bdist_msi", "bdist_rpm",
            "bdist_wheel", "bdist_wininst", "sdist",
        ),
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
    # We need this column to allow us to handle the currently existing "double"
    # sdists that exist in our database. Eventually we should try to get rid
    # of all of them and then remove this column.
    allow_multiple_sdist = Column(
        Boolean,
        nullable=False,
        server_default=sql.false(),
    )

    # TODO: Once Legacy PyPI is gone, then we should remove this column
    #       completely as we no longer use it.
    downloads = Column(Integer, server_default=sql.text("0"))

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

    Column("name", Text()),
    Column("version", Text()),
    Column("trove_id", Integer(), ForeignKey("trove_classifiers.id")),

    ForeignKeyConstraint(
        ["name", "version"],
        ["releases.name", "releases.version"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    ),

    Index("rel_class_name_idx", "name"),
    Index("rel_class_name_version_idx", "name", "version"),
    Index("rel_class_trove_id_idx", "trove_id"),
    Index("rel_class_version_id_idx", "version"),
)


class JournalEntry(db.ModelBase):

    __tablename__ = "journals"

    @declared_attr
    def __table_args__(cls):  # noqa
        return (
            Index(
                "journals_changelog",
                "submitted_date", "name", "version", "action",
            ),
            Index("journals_id_idx", "id"),
            Index("journals_name_idx", "name"),
            Index("journals_version_idx", "version"),
            Index(
                "journals_latest_releases",
                "submitted_date", "name", "version",
                postgresql_where=(
                    (cls.version != None) & (cls.action == "new release")  # noqa
                ),
            ),
        )

    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(Text)
    version = Column(Text)
    action = Column(Text)
    submitted_date = Column(
        DateTime(timezone=False),
        nullable=False,
        server_default=sql.func.now(),
    )
    _submitted_by = Column(
        "submitted_by",
        CIText,
        ForeignKey(
            "accounts_user.username",
            onupdate="CASCADE",
        ),
    )
    submitted_by = orm.relationship(User)
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
        DateTime(timezone=False),
        nullable=False,
        server_default=sql.func.now(),
    )
    name = Column(Text, unique=True, nullable=False)
    _blacklisted_by = Column(
        "blacklisted_by",
        UUID(as_uuid=True),
        ForeignKey("accounts_user.id"),
    )
    blacklisted_by = orm.relationship(User)
    comment = Column(Text, nullable=False, server_default="")
