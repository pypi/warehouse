# SPDX-License-Identifier: Apache-2.0
"""
Remove vestigial organizations admin flag

Revision ID: 6b38ccac39af
Revises: a3b1c4d5e6f7
Create Date: 2026-06-18 14:27:05.721228
"""

from alembic import op

revision = "6b38ccac39af"
down_revision = "a3b1c4d5e6f7"

# Note: It is VERY important to ensure that a migration does not lock for a
#       long period of time and to ensure that each individual migration does
#       not break compatibility with the *previous* version of the code base.
#       This is because the migrations will be ran automatically as part of the
#       deployment process, but while the previous version of the code is still
#       up and running. Thus backwards incompatible changes must be broken up
#       over multiple migrations inside of multiple pull requests in order to
#       phase them in over multiple deploys.
#
#       By default, migrations cannot wait more than 4s on acquiring a lock
#       and each individual statement cannot take more than 5s. This helps
#       prevent situations where a slow migration takes the entire site down.
#
#       If you need to increase this timeout for a migration, you can do so
#       by adding:
#
#           op.execute("SET statement_timeout = 5000")
#           op.execute("SET lock_timeout = 4000")
#
#       To whatever values are reasonable for this migration as part of your
#       migration.


def upgrade():
    op.execute("DELETE FROM admin_flags WHERE id = 'disable-organizations'")


def downgrade():
    op.execute("""
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            'disable-organizations',
            'Disallow ALL functionality for Organizations',
            FALSE,
            FALSE
        )
    """)
