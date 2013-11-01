# Copyright 2013 Donald Stufft
#
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
from __future__ import absolute_import, division, print_function
from __future__ import unicode_literals

import enum

from citext import CIText
from sqlalchemy import (
    Table, Column, CheckConstraint, ForeignKey, Index, UniqueConstraint,
    ForeignKeyConstraint, Sequence,
)
from sqlalchemy import Boolean, DateTime, Integer, UnicodeText
from sqlalchemy import sql

from warehouse.application import Warehouse


class ReleaseDependencyKind(int, enum.Enum):

    requires = 1  # Unused
    provides = 2  # Unused
    obsoletes = 3  # Unused
    requires_dist = 4
    provides_dist = 5
    obsoletes_dist = 6  # Unused
    requires_external = 7  # Unused

    # WHY
    project_url = 8


classifiers = Table(
    "trove_classifiers",
    Warehouse.metadata,

    Column(
        "id",
        Integer(),
        autoincrement=False,
        primary_key=True,
        nullable=False,
    ),
    Column("classifier", UnicodeText()),
    Column("l2", Integer()),
    Column("l3", Integer()),
    Column("l4", Integer()),
    Column("l5", Integer()),

    UniqueConstraint("classifier", name="trove_classifiers_classifier_key"),

    Index("trove_class_id_idx", "id"),
    Index("trove_class_class_idx", "classifier"),
)


release_classifiers = Table(
    "release_classifiers",
    Warehouse.metadata,

    Column("name", UnicodeText()),
    Column("version", UnicodeText()),
    Column("trove_id", Integer(), ForeignKey("trove_classifiers.id")),

    ForeignKeyConstraint(
        ["name", "version"],
        ["releases.name", "releases.version"],
        onupdate="CASCADE",
    ),

    Index("rel_class_name_idx", "name"),
    Index("rel_class_version_id_idx", "version"),
    Index("rel_class_name_version_idx", "name", "version"),
    Index("rel_class_trove_id_idx", "trove_id"),
)


packages = Table(
    "packages",
    Warehouse.metadata,

    Column("name", UnicodeText(), primary_key=True, nullable=False),
    Column("stable_version", UnicodeText()),
    Column("normalized_name", UnicodeText()),
    Column("autohide", Boolean(), server_default=sql.true()),
    Column("comments", Boolean(), server_default=sql.true()),
    Column("bugtrack_url", UnicodeText()),
    Column(
        "hosting_mode",
        UnicodeText(),
        nullable=False,
        server_default="pypi-explicit",
    ),
    Column(
        "created",
        DateTime(),
        nullable=False,
        server_default=sql.func.now(),
    ),

    # Validate that packages begin and end with an alpha numeric and contain
    #   only alpha numeric, ., _, and -.
    CheckConstraint(
        "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'",
        name="packages_valid_name",
    ),
)

releases = Table(
    "releases",
    Warehouse.metadata,

    Column(
        "name",
        UnicodeText(),
        ForeignKey("packages.name", onupdate="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column("version", UnicodeText(), primary_key=True, nullable=False),
    Column("author", UnicodeText()),
    Column("author_email", UnicodeText()),
    Column("maintainer", UnicodeText()),
    Column("maintainer_email", UnicodeText()),
    Column("home_page", UnicodeText()),
    Column("license", UnicodeText()),
    Column("summary", UnicodeText()),
    Column("description", UnicodeText()),
    Column("keywords", UnicodeText()),
    Column("platform", UnicodeText()),
    Column("download_url", UnicodeText()),
    Column("_pypi_ordering", Integer()),
    Column("_pypi_hidden", Boolean()),
    Column("description_html", UnicodeText()),
    Column(
        "cheesecake_installability_id",
        Integer(),
        ForeignKey("cheesecake_main_indices.id"),
    ),
    Column(
        "cheesecake_documentation_id",
        Integer(),
        ForeignKey("cheesecake_main_indices.id"),
    ),
    Column(
        "cheesecake_code_kwalitee_id",
        Integer(),
        ForeignKey("cheesecake_main_indices.id"),
    ),
    Column("requires_python", UnicodeText()),
    Column("description_from_readme", Boolean()),
    Column(
        "created",
        DateTime(),
        nullable=False,
        server_default=sql.func.now(),
    ),

    Index("release_name_idx", "name"),
    Index("release_version_idx", "version"),
    Index("release_name_created_idx", "name", "version"),
    Index("release_pypi_hidden_idx", "_pypi_hidden"),
)


release_dependencies = Table(
    "release_dependencies",
    Warehouse.metadata,

    Column("name", UnicodeText()),
    Column("version", UnicodeText()),
    Column("kind", Integer()),
    Column("specifier", UnicodeText()),

    ForeignKeyConstraint(
        ["name", "version"],
        ["releases.name", "releases.version"],
        onupdate="CASCADE",
    ),

    Index("rel_dep_name_idx", "name"),
    Index("rel_dep_name_version_idx", "name", "version"),
    Index("rel_dep_name_version_kind_idx", "name", "version", "kind"),
)


release_files = Table(
    "release_files",
    Warehouse.metadata,

    Column("name", UnicodeText()),
    Column("version", UnicodeText()),
    Column("python_version", UnicodeText()),
    Column("packagetype", UnicodeText()),
    Column("comment_text", UnicodeText()),
    Column("filename", UnicodeText()),
    Column("md5_digest", UnicodeText()),
    Column("downloads", Integer(), server_default=sql.text("0")),
    Column("upload_time", DateTime()),

    UniqueConstraint("filename", name="release_files_filename_key"),
    UniqueConstraint("md5_digest", name="release_files_md5_digest_key"),

    ForeignKeyConstraint(
        ["name", "version"],
        ["releases.name", "releases.version"],
        onupdate="CASCADE",
    ),

    Index("release_files_name_idx", "name"),
    Index("release_files_version_idx", "version"),
    Index("release_files_name_version_idx", "name", "version"),
    Index("release_files_packagetype_idx", "packagetype"),
)


description_urls = Table(
    "description_urls",
    Warehouse.metadata,

    Column("id", Integer(), primary_key=True, nullable=False),
    Column("name", UnicodeText()),
    Column("version", UnicodeText()),
    Column("url", UnicodeText()),

    ForeignKeyConstraint(
        ["name", "version"],
        ["releases.name", "releases.version"],
        onupdate="CASCADE",
    ),

    Index("description_urls_name_idx", "name"),
    Index("description_urls_name_version_idx", "name", "version"),
)


roles = Table(
    "roles",
    Warehouse.metadata,

    Column("role_name", UnicodeText()),
    Column(
        "user_name",
        CIText(),
        ForeignKey("accounts_user.username", onupdate="CASCADE"),
    ),
    Column(
        "package_name",
        UnicodeText(),
        ForeignKey("packages.name", onupdate="CASCADE"),
    ),

    Index("roles_pack_name_idx", "package_name"),
    Index("roles_user_name_idx", "user_name"),
)


journals = Table(
    "journals",
    Warehouse.metadata,

    Column("id", Integer(), Sequence("journals_id_seq")),
    Column("name", UnicodeText()),
    Column("version", UnicodeText()),
    Column("action", UnicodeText()),
    Column("submitted_date", DateTime()),
    Column("submitted_by", CIText()),  # Needs a FK to accounts_user
    Column("submitted_from", UnicodeText()),

    Index("journals_name_idx", "name"),
    Index("journals_version_idx", "version"),
    Index("journals_changelog", "submitted_date", "name", "version", "action"),
    Index("journals_latest_releases", "submitted_date", "name", "version"),
)


cheesecake_main_indices = Table(
    "cheesecake_main_indices",
    Warehouse.metadata,

    Column("id", Integer(), primary_key=True, nullable=False),
    Column("absolute", Integer(), nullable=False),
    Column("relative", Integer(), nullable=False),
)
