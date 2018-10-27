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
"""
migrate projects and releases to surrogate primary_key

Revision ID: ee5b8f66a223
Revises: e82c3a017d60
Create Date: 2018-10-27 16:31:38.859484
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "ee5b8f66a223"
down_revision = "e82c3a017d60"


def upgrade():
    op.add_column(
        "packages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )
    op.add_column(
        "releases",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )
    op.add_column(
        "roles",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "releases",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "release_files",
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "release_dependencies",
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "release_classifiers",
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.execute(
        """ UPDATE releases
            SET project_id = packages.id
            FROM packages
            WHERE releases.name = packages.name
        """
    )
    op.execute(
        """ UPDATE roles
            SET project_id = packages.id
            FROM packages
            WHERE
                packages.name = roles.package_name
        """
    )
    op.execute(
        """ UPDATE release_files
            SET release_id = releases.id
            FROM releases
            WHERE
                release_files.name = releases.name
                AND release_files.version = releases.version
        """
    )
    op.execute(
        """ DELETE FROM release_dependencies
            WHERE
                name IS NULL AND version IS NULL
        """
    )
    op.execute(
        """ UPDATE release_dependencies
            SET release_id = releases.id
            FROM releases
            WHERE
                release_dependencies.name = releases.name
                AND release_dependencies.version = releases.version
        """
    )
    op.execute(
        """ UPDATE release_classifiers
            SET release_id = releases.id
            FROM releases
            WHERE
                release_classifiers.name = releases.name
                AND release_classifiers.version = releases.version
        """
    )

    op.alter_column("releases", "project_id", nullable=False)
    op.alter_column("roles", "package_name", nullable=False)
    op.alter_column("release_files", "release_id", nullable=False)
    op.alter_column("release_dependencies", "release_id", nullable=False)
    op.alter_column("release_classifiers", "release_id", nullable=False)

    op.drop_constraint(
        "release_classifiers_name_fkey", "release_classifiers", type_="foreignkey"
    )
    op.drop_constraint(
        "release_dependencies_name_fkey", "release_dependencies", type_="foreignkey"
    )
    op.drop_constraint("release_files_name_fkey", "release_files", type_="foreignkey")
    op.drop_constraint("releases_name_fkey", "releases", type_="foreignkey")

    op.execute("ALTER TABLE packages DROP CONSTRAINT packages_pkey CASCADE")
    op.create_primary_key(None, "packages", ["id"])
    op.create_index(
        "release_normalized_name_version_idx",
        "releases",
        [sa.text("normalize_pep426_name(name)"), "version"],
        unique=True,
    )
    op.execute("ALTER TABLE releases DROP CONSTRAINT releases_pkey CASCADE")
    op.create_primary_key(None, "releases", ["id"])

    op.create_foreign_key(
        None,
        "releases",
        "packages",
        ["project_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        None,
        "roles",
        "packages",
        ["project_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        None,
        "release_files",
        "releases",
        ["release_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        None,
        "release_dependencies",
        "releases",
        ["release_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        None,
        "release_classifiers",
        "releases",
        ["release_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
