# SPDX-License-Identifier: Apache-2.0
"""
Add pep440_is_prerelease

Revision ID: e7b09b5c089d
Revises: be4cf6b58557
Create Date: 2016-12-03 15:04:40.251609
"""

from alembic import op

revision = "e7b09b5c089d"
down_revision = "be4cf6b58557"


def upgrade():
    op.execute("""
        CREATE FUNCTION pep440_is_prerelease(text) returns boolean as $$
                SELECT lower($1) ~* '(a|b|rc|dev|alpha|beta|c|pre|preview)'
            $$
            LANGUAGE SQL
            IMMUTABLE
            RETURNS NULL ON NULL INPUT;
    """)


def downgrade():
    op.execute("DROP FUNCTION pep440_is_prerelease")
