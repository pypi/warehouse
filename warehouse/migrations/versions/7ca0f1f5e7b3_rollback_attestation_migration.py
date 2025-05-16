# SPDX-License-Identifier: Apache-2.0
"""
Rollback attestation migration

Revision ID: 7ca0f1f5e7b3
Revises: 7f0c9f105f44
Create Date: 2024-08-21 19:52:40.084048
"""


from alembic import op

revision = "7ca0f1f5e7b3"
down_revision = "7f0c9f105f44"


def upgrade():
    op.drop_table("attestation")


def downgrade():
    pass
