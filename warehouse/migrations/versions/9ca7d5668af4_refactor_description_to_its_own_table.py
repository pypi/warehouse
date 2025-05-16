# SPDX-License-Identifier: Apache-2.0
"""
Refactor description to its own table

Revision ID: 9ca7d5668af4
Revises: 42f0409bb702
Create Date: 2019-05-10 16:19:04.008388
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "9ca7d5668af4"
down_revision = "42f0409bb702"


def upgrade():
    op.execute("SET statement_timeout = 0")
    op.create_table(
        "release_descriptions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("raw", sa.Text(), nullable=False),
        sa.Column("html", sa.Text(), nullable=False),
        sa.Column("rendered_by", sa.Text(), nullable=False),
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "releases",
        sa.Column("description_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        None,
        "releases",
        "release_descriptions",
        ["description_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )

    # Backfill our data into the description table.
    op.execute(
        """ WITH inserted_descriptions AS (
                INSERT INTO release_descriptions
                        (content_type, raw, html, rendered_by, release_id)
                    SELECT
                        description_content_type, COALESCE(description, ''), '', '', id
                    FROM releases
                    RETURNING release_id, id AS description_id
            )
            UPDATE releases
            SET description_id = ids.description_id
            FROM inserted_descriptions AS ids
            WHERE id = release_id
        """
    )

    op.alter_column("releases", "description_id", nullable=False)

    op.drop_column("releases", "description_content_type")
    op.drop_column("releases", "description")
    op.drop_column("release_descriptions", "release_id")


def downgrade():
    raise RuntimeError(f"Cannot downgrade past revision: {revision!r}")
