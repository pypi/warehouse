# SPDX-License-Identifier: Apache-2.0
"""
Move existing blacklisted projects into DB

Revision ID: 1e2ccd34f539
Revises: b6a20b9c888d
Create Date: 2017-09-16 04:26:23.844405
"""

from alembic import op

revision = "1e2ccd34f539"
down_revision = "b6a20b9c888d"


def upgrade():
    # Fix the trigger execution.
    op.execute("DROP TRIGGER normalize_blacklist ON blacklist")
    op.execute(""" CREATE TRIGGER normalize_blacklist
            BEFORE INSERT OR UPDATE ON blacklist
            FOR EACH ROW EXECUTE PROCEDURE ensure_normalized_blacklist();
        """)

    # Insert our default values, taken from existing legacy code.
    op.execute("INSERT INTO blacklist (name) VALUES ('requirements.txt')")
    op.execute("INSERT INTO blacklist (name) VALUES ('rrequirements.txt')")


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
