# SPDX-License-Identifier: Apache-2.0
"""
Only recompute projects.total_size when a file's size changes

Revision ID: 2c0c003dbc2f
Revises: a1c4b5219d5e
Create Date: 2026-10-15 09:10:08.959314
"""

from alembic import op

revision = "2c0c003dbc2f"
down_revision = "a1c4b5219d5e"


def upgrade():
    op.execute("""CREATE OR REPLACE TRIGGER update_project_total_size_release_files
            AFTER INSERT OR DELETE OR UPDATE OF size ON release_files
            FOR EACH ROW EXECUTE PROCEDURE projects_total_size_release_files();
        """)


def downgrade():
    op.execute("""CREATE OR REPLACE TRIGGER update_project_total_size_release_files
            AFTER INSERT OR UPDATE OR DELETE ON release_files
            FOR EACH ROW EXECUTE PROCEDURE projects_total_size_release_files();
        """)
