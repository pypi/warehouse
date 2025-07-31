# SPDX-License-Identifier: Apache-2.0
"""
rollback attestations again

Revision ID: dcf1e3986782
Revises: 4037669366ca
Create Date: 2024-09-03 18:04:17.149056
"""

from alembic import op

revision = "dcf1e3986782"
down_revision = "4037669366ca"


def upgrade():
    op.drop_table("attestation")


def downgrade():
    pass
