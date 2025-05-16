# SPDX-License-Identifier: Apache-2.0
"""
create role invitation table

Revision ID: 80018e46c5a4
Revises: 87509f4ae027
Create Date: 2020-06-28 14:53:07.803972
"""
import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "80018e46c5a4"
down_revision = "87509f4ae027"


def upgrade():
    op.create_table(
        "role_invitations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("invite_status", sa.Text(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "project_id", name="_role_invitations_user_project_uc"
        ),
    )
    op.create_index(
        "role_invitations_user_id_idx", "role_invitations", ["user_id"], unique=False
    )


def downgrade():
    op.drop_index("role_invitations_user_id_idx", table_name="role_invitations")
    op.drop_table("role_invitations")
