# SPDX-License-Identifier: Apache-2.0
"""
Backfill ReleaseURLs

Revision ID: 94c844c2da96
Revises: 7a8c380cefa4
Create Date: 2022-06-10 23:54:30.955026
"""

from alembic import op

revision = "94c844c2da96"
down_revision = "7a8c380cefa4"


def upgrade():
    op.create_check_constraint(
        "release_urls_valid_name", "release_urls", "char_length(name) BETWEEN 1 AND 32"
    )
    op.execute(r"""
        INSERT INTO release_urls (release_id, name, url)
            SELECT release_id,
                (regexp_match(specifier, '^([^,]+)\s*,\s*(.*)$'))[1],
                (regexp_match(specifier, '^([^,]+)\s*,\s*(.*)$'))[2]
            FROM release_dependencies
            WHERE release_dependencies.kind = 8
            ON CONFLICT ON CONSTRAINT release_urls_release_id_name_key
            DO NOTHING;
        """)


def downgrade():
    pass
