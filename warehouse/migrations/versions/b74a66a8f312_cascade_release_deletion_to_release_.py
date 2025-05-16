# SPDX-License-Identifier: Apache-2.0
"""
Cascade Release deletion to Release Classifiers

Revision ID: b74a66a8f312
Revises: 29d87a24d79e
Create Date: 2018-03-09 22:55:38.166123
"""

from alembic import op

revision = "b74a66a8f312"
down_revision = "29d87a24d79e"


def upgrade():
    op.execute(
        "ALTER TABLE release_classifiers "
        "DROP CONSTRAINT IF EXISTS release_classifiers_name_fkey"
    )
    op.create_foreign_key(
        "release_classifiers_name_fkey",
        "release_classifiers",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(
        "release_classifiers_name_fkey", "release_classifiers", type_="foreignkey"
    )
    op.create_foreign_key(
        "release_classifiers_name_fkey",
        "release_classifiers",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
    )
