# SPDX-License-Identifier: Apache-2.0
"""
Add a table to hold blacklisted projects

Revision ID: b6a20b9c888d
Revises: 5b3f9e687d94
Create Date: 2017-09-15 16:24:03.201478
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b6a20b9c888d"
down_revision = "5b3f9e687d94"


def upgrade():
    op.create_table(
        "blacklist",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("blacklisted_by", postgresql.UUID(), nullable=True),
        sa.Column("comment", sa.Text(), server_default="", nullable=False),
        sa.CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'::text",
            name="blacklist_valid_name",
        ),
        sa.ForeignKeyConstraint(["blacklisted_by"], ["accounts_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Setup a trigger that will ensure that we never commit a name that hasn't
    # been normalized to our blacklist.
    op.execute(""" CREATE OR REPLACE FUNCTION ensure_normalized_blacklist()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.name = normalize_pep426_name(NEW.name);
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
    op.execute(""" CREATE TRIGGER normalize_blacklist
            AFTER INSERT OR UPDATE OR DELETE ON blacklist
            FOR EACH ROW EXECUTE PROCEDURE ensure_normalized_blacklist();
        """)


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
