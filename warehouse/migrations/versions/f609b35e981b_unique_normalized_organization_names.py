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
Unique normalized organization names

Revision ID: f609b35e981b
Revises: 4f8982e60deb
Create Date: 2025-04-21 16:23:05.015207
"""

import sqlalchemy as sa

from alembic import op

revision = "f609b35e981b"
down_revision = "4f8982e60deb"


def upgrade():
    op.add_column(
        "organizations", sa.Column("normalized_name", sa.String(), nullable=True)
    )
    op.execute(
        """
        UPDATE organizations
        SET normalized_name = normalize_pep426_name(name)
        """
    )
    op.alter_column("organizations", "normalized_name", nullable=False)
    op.create_unique_constraint(None, "organizations", ["normalized_name"])

    op.execute(
        """ CREATE OR REPLACE FUNCTION maintain_organizations_normalized_name()
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
        """ CREATE TRIGGER organizations_update_normalized_name
            BEFORE INSERT OR UPDATE OF name ON organizations
            FOR EACH ROW
            EXECUTE PROCEDURE maintain_organizations_normalized_name()
        """
    )


def downgrade():
    op.drop_constraint(None, "organizations", type_="unique")
    op.drop_column("organizations", "normalized_name")
