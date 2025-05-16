# SPDX-License-Identifier: Apache-2.0
"""
Cascade deletes from Project/Release/File to Verdicts

Revision ID: f47d2f06c13e
Revises: 061ff3d24c22
Create Date: 2020-02-20 17:28:36.194480
"""

from alembic import op

revision = "f47d2f06c13e"
down_revision = "061ff3d24c22"


def upgrade():
    op.drop_constraint(
        "malware_verdicts_project_id_fkey", "malware_verdicts", type_="foreignkey"
    )
    op.drop_constraint(
        "malware_verdicts_release_id_fkey", "malware_verdicts", type_="foreignkey"
    )
    op.drop_constraint(
        "malware_verdicts_file_id_fkey", "malware_verdicts", type_="foreignkey"
    )
    op.create_foreign_key(
        "malware_verdicts_project_id_fkey",
        "malware_verdicts",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "malware_verdicts_release_id_fkey",
        "malware_verdicts",
        "releases",
        ["release_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "malware_verdicts_file_id_fkey",
        "malware_verdicts",
        "release_files",
        ["file_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(
        "malware_verdicts_file_id_fkey", "malware_verdicts", type_="foreignkey"
    )
    op.drop_constraint(
        "malware_verdicts_release_id_fkey", "malware_verdicts", type_="foreignkey"
    )
    op.drop_constraint(
        "malware_verdicts_project_id_fkey", "malware_verdicts", type_="foreignkey"
    )
    op.create_foreign_key(
        "malware_verdicts_file_id_fkey",
        "malware_verdicts",
        "release_files",
        ["file_id"],
        ["id"],
    )
    op.create_foreign_key(
        "malware_verdicts_release_id_fkey",
        "malware_verdicts",
        "releases",
        ["release_id"],
        ["id"],
    )
    op.create_foreign_key(
        "malware_verdicts_project_id_fkey",
        "malware_verdicts",
        "projects",
        ["project_id"],
        ["id"],
    )
