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

from citext import CIText
from pyramid.security import Allow
from pyramid.threadlocal import get_current_request
from sqlalchemy import (
    CheckConstraint, Column, Enum, ForeignKey, ForeignKeyConstraint, Index,
    Boolean, DateTime, Integer, Table, Text,
)
from sqlalchemy import func, orm, sql
from sqlalchemy.orm.exc import NoResultFound
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
        ForeignKey("accounts_user.username", onupdate="CASCADE"),
    )
    package_name = Column(
        Text,
        ForeignKey("packages.name", onupdate="CASCADE"),
    )

    user = orm.relationship(User, lazy=False)
    project = orm.relationship("Project", lazy=False)


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
    )

    def __getitem__(self, version):
        session = orm.object_session(self)

        try:
            return (
                session.query(Release)
                       .filter((Release.project == self) &
                               (Release.version == version))
                       .one()
            )
        except NoResultFound:
            raise KeyError from None

    def __acl__(self):
        session = orm.object_session(self)
        acls = []

        # Get all of the users for this project.
        query = session.query(Role).filter(Role.project == self)
        query = query.options(orm.lazyload("project"))
        query = query.options(orm.joinedload("user").lazyload("emails"))
        for role in sorted(
                query.all(),
                key=lambda x: ["Owner", "Maintainer"].index(x.role_name)):
            acls.append((Allow, role.user.id, ["upload"]))

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
        ForeignKey("packages.name", onupdate="CASCADE"),
        primary_key=True,
    )
    version = Column(Text, primary_key=True)
    author = Column(Text)
    author_email = Column(Text)
    maintainer = Column(Text)
    maintainer_email = Column(Text)
    home_page = Column(Text)
    license = Column(Text)
    summary = Column(Text)
    description = Column(Text)
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

    _classifiers = orm.relationship(
        Classifier,
        backref="project_releases",
        secondary=lambda: release_classifiers,
        order_by=Classifier.classifier,
    )
    classifiers = association_proxy("_classifiers", "classifier")

    files = orm.relationship(
        "File",
        backref="release",
        cascade="all, delete-orphan",
        lazy="dynamic",
        order_by=lambda: File.filename,
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
        order_by=lambda: JournalEntry.submitted_date.desc(),
        # TODO: We have uselist=False here which raises a warning because
        # multiple items were returned. This should only be temporary because
        # we should add a nullable FK to JournalEntry so we don't need to rely
        # on ordering and implicitly selecting the first object to make this
        # happen,
        uselist=False,
        viewonly=True,
    )

    @property
    def urls(self):
        _urls = OrderedDict()

        if self.home_page:
            _urls["Homepage"] = self.home_page

        for urlspec in self.project_urls:
            name, url = urlspec.split(",", 1)
            _urls[name] = url

        if self.download_url and "Download" not in _urls:
            _urls["Download"] = self.download_url

        return _urls

    @property
    def has_meta(self):
        return any([self.keywords])


class File(db.Model):

    __tablename__ = "release_files"
    __table_args__ = (
        ForeignKeyConstraint(
            ["name", "version"],
            ["releases.name", "releases.version"],
            onupdate="CASCADE",
        ),

        CheckConstraint("sha256_digest ~* '^[A-F0-9]{64}$'"),

        Index("release_files_name_idx", "name"),
        Index("release_files_name_version_idx", "name", "version"),
        Index("release_files_packagetype_idx", "packagetype"),
        Index("release_files_version_idx", "version"),
    )

    name = Column(Text)
    version = Column(Text)
    python_version = Column(Text)
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
    md5_digest = Column(Text, unique=True)
    sha256_digest = Column(CIText, unique=True, nullable=False)
    downloads = Column(Integer, server_default=sql.text("0"))
    upload_time = Column(DateTime(timezone=False), server_default=func.now())

    @hybrid_property
    def pgp_path(self):
        return self.path + ".asc"

    @pgp_path.expression
    def pgp_path(self):
        return func.concat(self.path, ".asc")


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
