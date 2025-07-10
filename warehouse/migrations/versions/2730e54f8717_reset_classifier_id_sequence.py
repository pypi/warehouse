# SPDX-License-Identifier: Apache-2.0
"""
Reset Classifier ID sequence

Revision ID: 2730e54f8717
Revises: 8fd3400c760f
Create Date: 2018-03-14 16:34:38.151300
"""

from alembic import op

revision = "2730e54f8717"
down_revision = "8fd3400c760f"


def upgrade():
    op.execute(
        """
        SELECT setval('trove_classifiers_id_seq', max(id))
        FROM trove_classifiers;
    """
    )


def downgrade():
    pass
