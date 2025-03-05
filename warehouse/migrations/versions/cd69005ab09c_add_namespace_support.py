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
add namespace support

Revision ID: cd69005ab09c
Revises: 6cac7b706953
Create Date: 2025-02-19 12:38:52.758352
"""

import sqlalchemy as sa

from alembic import op

revision = "cd69005ab09c"
down_revision = "635b80625fc9"


def upgrade():
    op.create_table(
        "project_namespaces",
        sa.Column(
            "is_approved", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("normalized_name", sa.String(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column(
            "is_open", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "is_hidden", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'::text",
            name="project_namespaces_valid_name",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["project_namespaces.id"],
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["organizations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_index(
        op.f("ix_project_namespaces_parent_id"),
        "project_namespaces",
        ["parent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_namespaces_owner_id"),
        "project_namespaces",
        ["owner_id"],
        unique=False,
    )

    op.execute(
        """ CREATE OR REPLACE FUNCTION maintain_project_namespaces_normalized_name()
            RETURNS TRIGGER AS $$
                BEGIN
                    NEW.normalized_name :=  normalize_pep426_name(NEW.name);
                    RETURN NEW;
                END;
            $$
            LANGUAGE plpgsql
        """
    )

    op.execute(
        """ CREATE TRIGGER project_namespaces_update_normalized_name
            BEFORE INSERT OR UPDATE OF name ON project_namespaces
            FOR EACH ROW
            EXECUTE PROCEDURE maintain_project_namespaces_normalized_name()
        """
    )


def downgrade():
    op.drop_index(
        op.f("ix_project_namespaces_owner_id"), table_name="project_namespaces"
    )
    op.drop_index(
        op.f("ix_project_namespaces_parent_id"), table_name="project_namespaces"
    )
    op.drop_table("project_namespaces")
