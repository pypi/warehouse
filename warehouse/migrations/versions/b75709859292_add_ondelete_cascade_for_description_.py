# SPDX-License-Identifier: Apache-2.0
"""
add ondelete=cascade for description_urls

Revision ID: b75709859292
Revises: 7165e957cddc
Create Date: 2018-02-19 02:26:37.944376
"""

from alembic import op

revision = "b75709859292"
down_revision = "7165e957cddc"


def upgrade():
    op.execute(
        "ALTER TABLE description_urls "
        "DROP CONSTRAINT IF EXISTS description_urls_name_fkey"
    )
    op.create_foreign_key(
        "description_urls_name_fkey",
        "description_urls",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(
        "description_urls_name_fkey", "description_urls", type_="foreignkey"
    )
    op.create_foreign_key(
        "description_urls_name_fkey",
        "description_urls",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
    )
