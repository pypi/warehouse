# SPDX-License-Identifier: Apache-2.0
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
