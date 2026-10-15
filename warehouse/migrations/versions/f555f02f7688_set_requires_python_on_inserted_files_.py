# SPDX-License-Identifier: Apache-2.0
"""
Set requires_python on inserted files only

Revision ID: f555f02f7688
Revises: a1c4b5219d5e
Create Date: 2026-10-15 16:40:11.989846
"""

from alembic import op

revision = "f555f02f7688"
down_revision = "a1c4b5219d5e"


def upgrade():
    op.execute("""CREATE OR REPLACE FUNCTION set_release_files_requires_python()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.requires_python := (
                SELECT requires_python FROM releases WHERE id = NEW.release_id
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """)
    op.execute("""CREATE OR REPLACE TRIGGER release_files_requires_python
            BEFORE INSERT ON release_files
            FOR EACH ROW EXECUTE PROCEDURE set_release_files_requires_python();
        """)


def downgrade():
    op.execute("""CREATE OR REPLACE TRIGGER release_files_requires_python
            AFTER INSERT ON release_files
            FOR EACH ROW EXECUTE PROCEDURE update_release_files_requires_python();
        """)
    op.execute("DROP FUNCTION set_release_files_requires_python();")
