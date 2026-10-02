# SPDX-License-Identifier: Apache-2.0
"""
Move Project.normalized_name to a regular column

Revision ID: 8bee9c119e41
Revises: 5a095c98f812
Create Date: 2022-06-27 14:48:16.619143
"""

import sqlalchemy as sa

from alembic import op

revision = "8bee9c119e41"
down_revision = "5a095c98f812"


def upgrade():
    op.add_column("projects", sa.Column("normalized_name", sa.Text(), nullable=True))
    op.execute("""
        UPDATE projects
        SET normalized_name = normalize_pep426_name(name)
        """)
    op.alter_column("projects", "normalized_name", nullable=False)
    op.create_unique_constraint(None, "projects", ["normalized_name"])
    op.execute("DROP INDEX project_name_pep426_normalized")

    op.execute(""" CREATE OR REPLACE FUNCTION maintain_projects_normalized_name()
            RETURNS TRIGGER AS $$
                BEGIN
                    NEW.normalized_name :=  normalize_pep426_name(NEW.name);
                    RETURN NEW;
                END;
            $$
            LANGUAGE plpgsql
        """)

    op.execute(""" CREATE TRIGGER projects_update_normalized_name
            BEFORE INSERT OR UPDATE OF name ON projects
            FOR EACH ROW
            EXECUTE PROCEDURE maintain_projects_normalized_name()
        """)


def downgrade():
    op.execute(""" CREATE UNIQUE INDEX project_name_pep426_normalized
            ON projects
            (normalize_pep426_name(name))
        """)
    op.drop_constraint(None, "projects", type_="unique")
    op.drop_column("projects", "normalized_name")
