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

from citext import CIText
from sqlalchemy import (
    CheckConstraint, Column, ForeignKey, Index, Boolean, DateTime, Integer,
    Text,
)
from sqlalchemy import orm, sql
from sqlalchemy.ext.declarative import declared_attr

from warehouse import db
from warehouse.accounts.models import User
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
