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

from citext import CIText
from pyramid.threadlocal import get_current_registry
from sqlalchemy import (
    CheckConstraint, Column, Enum, ForeignKey, ForeignKeyConstraint, Index,
    Boolean, DateTime, Integer, Table, Text,
)
from sqlalchemy import func, orm, sql
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.hybrid import hybrid_property

from warehouse import db
from warehouse.accounts.models import User
from warehouse.classifiers.models import Classifier
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
                Project.normalized_name == func.lower(
                    func.regexp_replace(project, "_", "-", "ig")
                )
            ).one()
        except NoResultFound:
            raise KeyError from None


class Project(db.ModelBase):

    __tablename__ = "packages"
    __table_args__ = (
        CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'::text",
            name="packages_valid_name",
        ),
    )

    __repr__ = make_repr("name")

    name = Column(Text, primary_key=True, nullable=False)
    normalized_name = Column(Text)
    stable_version = Column(Text)
    autohide = Column(Boolean, server_default=sql.true())
    comments = Column(Boolean, server_default=sql.true())
    bugtrack_url = Column(Text)
    hosting_mode = Column(Text, nullable=False, server_default="pypi-explicit")
    created = Column(
        DateTime(timezone=False),
        nullable=False,
        server_default=sql.func.now(),
    )

    releases = orm.relationship(
        "Release",
        backref="project",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __getitem__(self, version):
        try:
            return self.releases.filter(Release.version == version).one()
        except NoResultFound:
            raise KeyError from None


class Release(db.ModelBase):

    __tablename__ = "releases"

    @declared_attr
    def __table_args__(cls):  # noqa
        return (
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
    description_html = Column(Text)
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

    classifiers = orm.relationship(
        Classifier,
        backref="project_releases",
        secondary=lambda: release_classifiers,
        order_by=Classifier.classifier,
    )

    files = orm.relationship(
        "File",
        backref="release",
        cascade="all, delete-orphan",
        lazy="dynamic",
        order_by=lambda: File.filename,
    )


class File(db.Model):

    __tablename__ = "release_files"
    __table_args__ = (
        ForeignKeyConstraint(
            ["name", "version"],
            ["releases.name", "releases.version"],
            onupdate="CASCADE",
        ),

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
    md5_digest = Column(Text, unique=True)
    downloads = Column(Integer, server_default=sql.text("0"))
    upload_time = Column(DateTime(timezone=False))

    @hybrid_property
    def path(self):
        return "/".join([
            self.python_version,
            self.name[0],
            self.name,
            self.filename,
        ])

    @path.expression
    def path(self):
        return func.concat_ws(
            "/",
            self.python_version,
            func.substring(self.name, 1, 1),
            self.name,
            self.filename,
        )

    @hybrid_property
    def pgp_path(self):
        return self.path + ".asc"

    @pgp_path.expression
    def pgp_path(self):
        return func.concat(self.path, ".asc")

    @property
    def has_pgp_signature(self):
        # TODO: Move this into the database and elimnate the use of the
        #       threadlocal here.
        registry = get_current_registry()
        return registry["filesystems"]["packages"].exists(self.pgp_path)

    @property
    def size(self):
        # TODO: Move this into the database and eliminate the use of the
        #       threadlocal here.
        registry = get_current_registry()
        try:
            return registry["filesystems"]["packages"].getsize(self.path)
        except fs.errors.ResourceNotFoundError:
            # When running locally we probably don't have the files laying
            # around, in addition it's a sad fact that there are currently
            # some projects which have missing files. Once the size is moved
            # into the database this should no longer be an issue.
            return 0


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
    submitted_date = Column(DateTime(timezone=False))
    submitted_by = Column(
        CIText,
        ForeignKey(
            "accounts_user.username",
            onupdate="CASCADE",
        ),
    )
    submitted_from = Column(Text)
