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
    op.execute(
        """
        UPDATE projects
        SET normalized_name = normalize_pep426_name(name)
        """
    )
    op.alter_column("projects", "normalized_name", nullable=False)
    op.create_unique_constraint(None, "projects", ["normalized_name"])
    op.execute("DROP INDEX project_name_pep426_normalized")

    op.execute(
        """ CREATE OR REPLACE FUNCTION maintain_projects_normalized_name()
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
        """ CREATE TRIGGER projects_update_normalized_name
            BEFORE INSERT OR UPDATE OF name ON projects
            FOR EACH ROW
            EXECUTE PROCEDURE maintain_projects_normalized_name()
        """
    )


def downgrade():
    op.execute(
        """ CREATE UNIQUE INDEX project_name_pep426_normalized
            ON projects
            (normalize_pep426_name(name))
        """
    )
    op.drop_constraint(None, "projects", type_="unique")
    op.drop_column("projects", "normalized_name")
